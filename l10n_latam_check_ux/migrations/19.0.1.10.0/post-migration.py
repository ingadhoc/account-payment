"""Corrige las cadenas de operaciones de cheques que quedaron desordenadas.

Tickets 126339 / 126474 / 127441, tarea 73306. El fix de código que va en esta misma versión
evita que vuelva a pasar, pero no repara las cadenas ya desordenadas.

DETECCIÓN POR EL RECORRIDO DEL CHEQUE, NO POR FECHAS
    Hasta esta versión el default del campo de fecha de operación se evaluaba una sola vez al
    importar el módulo, así que todos los pagos preexistentes quedaron con el mismo timestamp.
    Esos cheques están EMPATADOS, no desordenados, y el desempate por ``id`` de
    ``_get_last_operation()`` los ordena bien: compararlos por fecha marcaría cientos de cheques
    sanos.

    El criterio es el propio recorrido: un cheque solo puede SALIR del diario donde está, y solo
    puede ENTRAR al diario destino de esa salida. Eso alcanza para reconstruir el orden real a
    partir de los datos, sin depender de ninguna fecha. Se corrige un cheque cuando esa
    reconstrucción existe, es única, y contradice el orden guardado.

    Cubre las dos formas que rompen la cadena y que por fecha no se distinguen de una cadena sana:
    el pago donde el cheque nace dejado de última (ticket 126339), y dos operaciones posteriores
    dadas vuelta entre sí porque una se creó en borrador antes y se confirmó después (127441).

    Cuando el recorrido es ambiguo —dos salidas posibles desde el mismo diario— o no cierra, el
    cheque no se toca y se lista al final. Preferimos dejar un cheque roto sin corregir antes que
    reordenar uno sano.

SOLO DONDE CAMBIA LA ÚLTIMA OPERACIÓN
    De la última operación salen el diario actual del cheque y el bloqueo para restablecer un pago
    a borrador: es todo lo que se ve de este orden. Un desorden que no la mueve solo afecta a la
    lista de operaciones, y lo genera el propio código —el ``timedelta`` que corre la pata saliente
    de un traspaso pareado—, así que vuelve a aparecer apenas se opere de nuevo. Corregirlo
    agrandaría el radio de escritura sobre bases de clientes sin arreglar nada que alguien vea, así
    que esos quedan afuera; el log los cuenta aparte.

``current_journal_id`` y ``company_id`` se recalculan solo sobre los cheques alcanzados: son
stored y su ``depends`` no incluye la fecha, así que reordenar no los dispara, pero un recompute
masivo movería cheques que hoy están bien (ver ticket 123455).
"""

import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

FECHA = "l10n_latam_move_check_ids_operation_date"
NO_VIGENTES = ("draft", "canceled")


def _diario_despues(payment):
    """Diario donde queda el cheque después de esta operación.

    Una entrada lo deja en su propio diario; una salida, en el diario destino del traspaso. Una
    entrega a un proveedor no tiene destino: ahí el cheque sale de la cartera.
    """
    if payment.payment_type == "inbound":
        return payment.journal_id
    return payment.destination_journal_id


def _vigentes(check):
    """Operaciones que cuentan para el orden, ya ordenadas como las lee el modelo.

    Mismo filtro y mismo desempate que ``_get_last_operation()``; si aquel cambia, esto cambia con
    él.
    """
    return (
        (check.payment_id + check.operation_ids)
        .filtered(lambda p: p.state not in NO_VIGENTES and p[FECHA])
        .sorted(key=lambda p: (p[FECHA], p.id))
    )


def _reconstruir_cadena(check, vigentes):
    """Orden real de las operaciones, siguiendo el paso del cheque por los diarios.

    Devuelve el recordset ordenado, o ``None`` si el recorrido no es único: ahí no hay forma de
    saber cuál es el orden bueno y el cheque queda sin tocar.
    """
    nacimiento = check.payment_id
    if nacimiento not in vigentes:
        return None
    orden = nacimiento
    restantes = vigentes - nacimiento
    diario = _diario_despues(nacimiento)
    while restantes:
        salidas = restantes.filtered(lambda p: p.payment_type == "outbound" and p.journal_id == diario)
        if len(salidas) != 1:
            return None
        orden += salidas
        restantes -= salidas
        diario = _diario_despues(salidas)
        if not diario:
            # Entrega a un proveedor o devolución al cliente: el cheque deja la cartera y la cadena
            # termina, así que no puede quedar ninguna operación suelta.
            return orden if not restantes else None
        entradas = restantes.filtered(lambda p: p.payment_type == "inbound" and p.journal_id == diario)
        if len(entradas) != 1:
            return None
        orden += entradas
        restantes -= entradas
        diario = _diario_despues(entradas)
    return orden


def clasificar(env):
    """Reparte los cheques de la base en los tres grupos que decide el script, sin escribir nada.

    Devuelve ``(ordenes, solo_visual, ambiguos, candidatos)``, donde ``ordenes`` mapea id de cheque
    a ``(cheque, orden_real)``. Está separado de ``migrate()`` para que el dry-run que se corre
    sobre copias de bases de clientes mida este criterio y no una copia suya.
    """
    # Prefiltro para no recorrer todos los cheques de la base. Marca los cheques donde, en el orden
    # guardado, alguna operación no arranca en el diario donde la anterior dejó el cheque. Es
    # implicado por el criterio de abajo —si la reconstrucción contradice el orden guardado, en
    # algún punto el recorrido se corta—, así que ninguna cadena desordenada se escapa. Puede traer
    # de más, que el ORM descarta.
    env.cr.execute(
        f"""
        WITH pares AS (
            SELECT check_id, payment_id FROM l10n_latam_check_account_payment_rel
             UNION
            SELECT id, payment_id FROM l10n_latam_check WHERE payment_id IS NOT NULL
        ),
        ordenadas AS (
            SELECT pares.check_id, pares.payment_id, p.journal_id,
                   ROW_NUMBER() OVER w AS pos,
                   -- Mismo criterio que _diario_despues(). Si los dos se separan, el prefiltro deja
                   -- de ser superconjunto y hay cadenas rotas que nunca llegan al ORM.
                   LAG(CASE WHEN p.payment_type = 'inbound'
                            THEN p.journal_id ELSE p.destination_journal_id END) OVER w AS diario_previo
              FROM pares
              JOIN account_payment p ON p.id = pares.payment_id
             WHERE p.state NOT IN %s AND p.{FECHA} IS NOT NULL
            WINDOW w AS (PARTITION BY pares.check_id ORDER BY p.{FECHA}, pares.payment_id)
        )
        -- El segundo disyunto necesita el nacimiento: un traspaso cuyo destino es su propio diario
        -- hace que todas las adyacencias cierren aunque el nacimiento no esté primero.
        SELECT DISTINCT o.check_id
          FROM ordenadas o
          JOIN l10n_latam_check chk ON chk.id = o.check_id
         WHERE (o.pos > 1 AND o.journal_id IS DISTINCT FROM o.diario_previo)
            OR (o.pos = 1 AND o.payment_id IS DISTINCT FROM chk.payment_id)
        """,
        (NO_VIGENTES,),
    )
    candidatos = env["l10n_latam.check"].browse([row[0] for row in env.cr.fetchall()])
    # Solo cheques de terceros: los propios no recorren diarios —nacen emitidos y se debitan—, así
    # que el criterio no aplica.
    candidatos = candidatos.filtered(lambda c: c.payment_method_code == "new_third_party_checks")
    # El concat de ``payment_id + operation_ids`` arma un recordset nuevo y pierde el prefetch, así
    # que sin esto cada cheque dispara su propio SELECT ancho. Traemos de una sola vez lo que miran
    # la reconstrucción y los recomputes del final.
    (candidatos.payment_id | candidatos.operation_ids).fetch(
        ["state", FECHA, "payment_type", "journal_id", "destination_journal_id"]
    )

    # Se clasifica antes de escribir porque un pago puede llevar varios cheques y corregir su fecha
    # ordena todas esas cadenas de una vez: evaluar el síntoma dentro del loop de escritura dejaría
    # al segundo cheque afuera del recompute, con la cadena bien y el cheque todavía en cartera.
    ordenes = {}
    ambiguos, solo_visual = [], []
    for check in candidatos:
        orden_real = _reconstruir_cadena(check, _vigentes(check))
        if orden_real is None:
            ambiguos.append(check.id)
            continue
        # Segundo candado: solo se corrige donde el desorden CAMBIA cuál es la última operación, que
        # es de donde salen el diario actual del cheque y el bloqueo para restablecer a borrador. Un
        # desorden que no mueve la última no lo ve nadie más que la lista de operaciones, y lo
        # genera el propio código —el ``timedelta`` que corre la pata saliente de un traspaso
        # pareado—, así que reaparece después de migrar: repararlo agranda el radio de escritura
        # sobre bases de clientes sin arreglar nada que se vea.
        if orden_real[-1:] == check._get_last_operation():
            if orden_real.ids != _vigentes(check).ids:
                solo_visual.append(check.id)
            continue
        ordenes[check.id] = (check, orden_real)
    return ordenes, solo_visual, ambiguos, candidatos


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ordenes, solo_visual, ambiguos, candidatos = clasificar(env)

    tocados = []
    for check, orden_real in ordenes.values():
        previa = orden_real[0][FECHA]
        # tracking_disable: account.payment es mail.thread, y cada write snapshotea todos sus campos
        # trackeados —algunos computados sobre apuntes contables—, no solo el que se toca.
        for payment in orden_real[1:].with_context(tracking_disable=True):
            if payment[FECHA] > previa:
                previa = payment[FECHA]
                continue
            previa += timedelta(seconds=1)
            _logger.info("Cheque %s: operación %s pasa de %s a %s", check.name, payment.name, payment[FECHA], previa)
            payment[FECHA] = previa
            tocados.append(payment.id)

    # Un pago puede llevar varios cheques, así que moverle la fecha reordena todas esas cadenas, no
    # solo la que motivó la escritura. El recompute va sobre todas: si se limitara a los corregidos,
    # un cheque vecino quedaría con la cadena movida y el diario actual viejo.
    tocados = env["account.payment"].browse(tocados)
    corregidos = env["l10n_latam.check"].browse(list(ordenes))
    afectados = corregidos | tocados.l10n_latam_move_check_ids | tocados.l10n_latam_new_check_ids
    afectados._compute_current_journal()
    afectados._compute_company_id()

    _logger.info(
        "Cadenas de cheques desordenadas: %s de %s candidato(s). Corregidos: %s",
        len(corregidos),
        len(candidatos),
        ", ".join(filter(None, corregidos.mapped("name"))) or "ninguno",
    )
    solo_visual = env["l10n_latam.check"].browse(solo_visual)
    if solo_visual:
        _logger.info(
            "Otros %s cheque(s) tienen la cadena desordenada sin que cambie la última operación; no se tocan: %s",
            len(solo_visual),
            ", ".join(filter(None, solo_visual.mapped("name"))),
        )
    ambiguos = env["l10n_latam.check"].browse(ambiguos)
    if ambiguos:
        # No es una alarma: un rechazo o una devolución no siguen el paso por diarios —una entrada
        # de recupero no es la pata de ninguna salida—, así que caen acá estando sanos. Se listan
        # porque también cae acá una cadena rota que no sabemos reordenar.
        _logger.info(
            "No se pudo reconstruir el recorrido de %s cheque(s) —rechazos y devoluciones caen acá "
            "estando sanos—, quedaron sin tocar: %s",
            len(ambiguos),
            ", ".join(filter(None, ambiguos.mapped("name"))),
        )

    # Mover un pago compartido puede desordenar la cadena de un cheque vecino que estaba sana, e
    # incluso la de uno ya corregido si el pago se movió dos veces. No se corrige en cascada; se
    # avisa para que no pase en silencio. La reconstrucción no depende de las fechas, así que la ya
    # calculada sigue valiendo.
    restantes = []
    for check in afectados:
        guardada = ordenes.get(check.id)
        orden_real = guardada[1] if guardada else _reconstruir_cadena(check, _vigentes(check))
        if orden_real and orden_real[-1:] != check._get_last_operation():
            restantes.append(check.id)
    restantes = env["l10n_latam.check"].browse(restantes)
    if restantes:
        _logger.warning(
            "Quedaron %s cheque(s) con la cadena desordenada, revisar a mano: %s",
            len(restantes),
            ", ".join(filter(None, restantes.mapped("name"))),
        )

    # Linea de resumen con un marcador fijo: es la que se consulta despues en Cloud Logging para
    # saber, por base y sin leer el log entero, si el script corrio y cuanto escribio. Se emite
    # siempre, incluso cuando no corrige nada — que es justo el caso que no se puede distinguir
    # desde los datos de "el script nunca corrio".
    _logger.info(
        "CHEQUES-127441 base=%s candidatos=%s corregidos=%s solo_visual=%s ambiguos=%s "
        "pagos_escritos=%s cheques_recalculados=%s sin_resolver=%s",
        cr.dbname,
        len(candidatos),
        len(corregidos),
        len(solo_visual),
        len(ambiguos),
        len(tocados),
        len(afectados),
        len(restantes),
    )
