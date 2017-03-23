# -*- coding: utf-8 -*-

""" 
    This file contains different utility functions that are not connected
    in any model but are used in specific situations
"""
def build_domain(comparefield, elements):
    domain = []

    for element in elements:
        if element.count(':'):
            accounts = element.split(':')
            fr_account = accounts[0]
            to_account = accounts[1]
            domain.append((comparefield, '>=', str(fr_account)))
            domain.append((comparefield, '<=', str(to_account)))
        else:
            if element.count('!'):
                element = element.strip('!')
                domain.append((comparefield, '!=', str(element)))
            else:
                if element == 'False':
                    domain.append((comparefield, '=', False))
                else:
                    domain.append((comparefield, 'ilike', str(element)))

    return domain
    
def translate_domain(domain_without_format, type):
    domain = []
    elements = domain_without_format.split(',')
    if type == 'accounts':
        domain = build_domain('partner_id.property_account_payable_id',elements)

    if type == 'city':
        domain = build_domain('partner_id.city',elements)

    if type == 'state_id':
        domain = build_domain('partner_id.state_id',elements)
    
    # if domain.count > 1:
    #     domain = ['&'] + domain

    return domain

