import json

from odoo import _, models
from odoo.exceptions import ValidationError


class ReSequenceWizard(models.TransientModel):
    _inherit = "account.resequence.wizard"

    def resequence(self):
        if self.ordering == "keep":
            new_names = [v["new_by_name"] for v in json.loads(self[0]["new_values"]).values()]
        else:
            new_names = [v["new_by_date"] for v in json.loads(self[0]["new_values"]).values()]

        duplicated_names = self.env["account.move"].search(
            [
                ("receiptbook_id", "=", self.move_ids.receiptbook_id.id),
                ("name", "in", new_names),
                ("id", "not in", self.move_ids.ids),
            ]
        )
        if duplicated_names:
            raise ValidationError(
                _("The following receipt names already exist:\n%s") % "\n".join(duplicated_names.mapped("name"))
            )

        original_move_ids = self.move_ids
        original_wizard = self[0].copy()

        for journal in original_move_ids.journal_id:
            move_ids = original_move_ids.filtered(lambda x: x.journal_id == journal)

            all_moves = json.loads(original_wizard.read()[0]["new_values"])

            # Filter only the moves for this journal
            filtered_moves = {str(mid.id): all_moves[str(mid.id)] for mid in move_ids if str(mid.id) in all_moves}

            # I have to write move_ids before new_values because is computed
            # and changes new_values
            self[0].write({"move_ids": move_ids})
            # Write as proper JSON string
            self[0].write({"new_values": json.dumps(filtered_moves)})

            super().resequence()
