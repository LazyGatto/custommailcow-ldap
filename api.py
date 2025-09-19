import sys
import logging

import requests

s = requests.session()

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
s.verify = False

def __post_request(url, json_data):
    api_url = f"{api_host}/{url}"
    headers = {'X-API-Key': api_key, 'Content-type': 'application/json'}

    req = s.post(api_url, headers=headers, json=json_data)
    rsp = req.json()
    req.close()

    if isinstance(rsp, list):
        rsp = rsp[0]

    if not "type" in rsp or not "msg" in rsp:
        sys.exit(f"API {url}: got response without type or msg from Mailcow API")

    if rsp['type'] != 'success':
        sys.exit(f"API {url}: {rsp['type']} - {rsp['msg']}")



def add_alias(address, goto, active=True):
    json_data = {
        'active': active,
        'address': address,
        'goto': goto,
        'sogo_visible': True
    }
    __post_request('api/v1/add/alias', json_data)
    logging.info(f"[ + ] [API] [ Alias ] {address} => {goto} (Active: {active}) - added alias in mailcow")

def edit_user(email, active=None):
    attr = {}
    if active is not None:
        attr['active'] = 1 if active else 0
    json_data = {
        'items': [email],
        'attr': attr
    }
    __post_request('api/v1/edit/mailbox', json_data)

def edit_alias(address, goto, active=None):
    attr = {}
    if active is not None:
        attr['active'] = 1 if active else 0
    attr['address'] = address
    attr['goto'] = goto
    json_data = {
        'items': [address],
        'attr': attr
    }
    __post_request('api/v1/edit/alias', json_data)    


def delete_alias(address):
    json_data = [address]
    __post_request('api/v1/delete/alias', json_data)
    logging.info(f"[DEL] [API] [ Alias ] {address} - deleting alias in mailcow")

# Returns (api_user_exists, api_user_active)
def check_user(email):
    url = f"{api_host}/api/v1/get/mailbox/{email}"
    headers = {'X-API-Key': api_key, 'Content-type': 'application/json'}
    req = s.get(url, headers=headers)
    rsp = req.json()
    req.close()

    if not isinstance(rsp, dict):
        sys.exit("API get/mailbox: got response of a wrong type")

    if not rsp:
        return False, False

    if 'active_int' not in rsp and rsp['type'] == 'error':
        sys.exit(f"API {url}: {rsp['type']} - {rsp['msg']}")

    return True, bool(rsp['active_int'])

# Returns (api_alias_exists, api_alias_address, api_alias_goto)
def check_alias(address):
    url = f"{api_host}/api/v1/get/alias/{address}"
    headers = {'X-API-Key': api_key, 'Content-type': 'application/json'}
    req = s.get(url, headers=headers)
    rsp = req.json()
    req.close()

    if not isinstance(rsp, dict):
        sys.exit("API get/alias: got response of a wrong type")

    if not rsp:
        return False, False, None, False

    if 'active_int' not in rsp and rsp['type'] == 'error':
        sys.exit(f"API {url}: {rsp['type']} - {rsp['msg']}")

    return True, rsp['address'], rsp['goto'], bool(rsp['active_int'])
