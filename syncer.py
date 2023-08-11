import datetime
import logging
import os
import sys
import time
from pathlib import Path
from string import Template

#DEBUG
import traceback

import ldap

import api
import filedb

logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%d.%m.%y %H:%M:%S', level=logging.INFO)
config = {}


def main():
    global config
    read_config()

    passdb_conf = read_dovecot_passdb_conf_template()
    plist_ldap = read_sogo_plist_ldap_template()
    extra_conf = read_dovecot_extra_conf()

    passdb_conf_changed = apply_config('conf/dovecot/ldap/passdb.conf', config_data=passdb_conf)
    extra_conf_changed = apply_config('conf/dovecot/extra.conf', config_data=extra_conf)
    plist_ldap_changed = apply_config('conf/sogo/plist_ldap', config_data=plist_ldap)

    if passdb_conf_changed or extra_conf_changed or plist_ldap_changed:
        logging.info(
            "One or more config files have been changed, please make sure to restart dovecot-mailcow and sogo-mailcow!")

    api.api_host = config['API_HOST']
    api.api_key = config['API_KEY']
    api.api_quota = config['API_QUOTA']

    while True:
        sync()
        interval = int(config['SYNC_INTERVAL'])
        logging.info(f"Sync finished, sleeping {interval} seconds before next cycle")
        time.sleep(interval)


def sync():
    ldap_connector = ldap.initialize(f"{config['LDAP_URI']}")
    ldap_connector.set_option(ldap.OPT_REFERRALS, 0)
    ldap_connector.simple_bind_s(config['LDAP_BIND_DN'], config['LDAP_BIND_DN_PASSWORD'])

    filedb.session_time = datetime.datetime.now()
    
    logging.info("=== Iterate LDAP Users (Mailboxes) ===")

    ldap_results = ldap_connector.search_s(config['LDAP_BASE_DN'], ldap.SCOPE_SUBTREE,
                                           config['LDAP_FILTER'],
                                           ['mail', 'displayName', 'userAccountControl'])

    for x in ldap_results:
        try:
            # LDAP Search still returns invalid objects, test instead of throw.
            if not x[0]:
                continue
            email = x[1]['mail'][0].decode()
            ldap_name = x[1]['displayName'][0].decode()
            ldap_active = False if int(x[1]['userAccountControl'][0].decode()) & 0b10 else True

            (db_user_exists, db_user_active) = filedb.check_user(email)
            (api_user_exists, api_user_active, api_name) = api.check_user(email)

            unchanged = True

            if not db_user_exists:
                filedb.add_user(email, ldap_active)
                (db_user_exists, db_user_active) = (True, ldap_active)
                logging.info(f"Added filedb user: {email} (Active: {ldap_active})")
                unchanged = False

            if not api_user_exists:
                api.add_user(email, ldap_name, ldap_active)
                (api_user_exists, api_user_active, api_name) = (True, ldap_active, ldap_name)
                logging.info(f"Added Mailcow user: {email} (Active: {ldap_active})")
                unchanged = False

            if db_user_active != ldap_active:
                filedb.user_set_active_to(email, ldap_active)
                logging.info(f"{'Activated' if ldap_active else 'Deactivated'} {email} in filedb")
                unchanged = False

            if api_user_active != ldap_active:
                api.edit_user(email, active=ldap_active)
                logging.info(f"{'Activated' if ldap_active else 'Deactivated'} {email} in Mailcow")
                unchanged = False

            if api_name != ldap_name:
                api.edit_user(email, name=ldap_name)
                logging.info(f"Changed name of {email} in Mailcow to {ldap_name}")
                unchanged = False

            if unchanged:
                logging.info(f"Checked user {email}, unchanged")

        except Exception:
            logging.info(f"Exception during handling of {x}")
            pass

    logging.info("=== Iterate LDAP Groups (Aliases) ===")

    ldap_results_groups = ldap_connector.search_s(config['LDAP_BASE_DN'], ldap.SCOPE_SUBTREE,
                                            config['LDAP_GROUP_FILTER'],
                                            ['member', 'mail'])

    for g in ldap_results_groups:
        try:
            if not g[0]:
                continue
            alias_address = g[1]['mail'][0].decode()

            # Iterate members of group
            group_members = []
            for m in g[1]['member']:
                member_cn = m.decode()
                member_mail_ldap = ldap_connector.search_s(config['LDAP_BASE_DN'], ldap.SCOPE_SUBTREE,
                                                config['LDAP_GROUP_MEMBER_FILTER'].replace("{MEMBER_CN}", member_cn),
                                                ['mail'])
                if member_mail_ldap[0][0] is not None:
                    member_mail = member_mail_ldap[0][1]['mail'][0].decode()
                    group_members.append(member_mail)

            alias_goto = ','.join(group_members)

            (api_alias_exists, api_alias_address, api_alias_goto, api_alias_active) = api.check_alias(alias_address)
            (db_alias_exists, db_alias_goto, db_alias_active) = filedb.check_alias(alias_address)

            unchanged = True

            if not db_alias_exists:
                filedb.add_alias(alias_address, alias_goto)
                (db_alias_exists, db_alias_goto) = (True, alias_goto)
                logging.info(f"Added filedb alias: {alias_address} (Goto: {alias_goto})")
                unchanged = False

            if not api_alias_exists:
                api.add_alias(alias_address, alias_goto)
                (api_alias_exists, api_alias_goto, api_alias_active) = (True, alias_goto, True)
                logging.info(f"Added Mailcow alias: {alias_address} (Goto: {alias_goto})")
                unchanged = False

            if db_alias_goto != alias_goto:
                filedb.edit_alias_goto(alias_address, alias_goto)
                logging.info(f"Changed filedb alias: {alias_address} (Goto: {alias_goto})")
                unchanged = False

            if api_alias_goto != alias_goto:
                api.edit_alias(alias_address, alias_goto, True)
                logging.info(f"Changed Mailcow alias: {alias_address} (Goto: {alias_goto})")
                unchanged = False
            
            if api_alias_exists and not api_alias_active:
                api.edit_alias(alias_address, alias_goto, True)
                logging.info(f"Activating Mailcow alias: {alias_address} (Goto: {alias_goto})")
                unchanged = False

            if unchanged:
                logging.info(f"Checked alias {alias_address}, unchanged")          

        except Exception:
            #DEBUG
            print(traceback.format_exc())
            #DEBUG
            logging.info(f"Exception during handling of {x}")
            pass            

    for email in filedb.get_unchecked_active_users():
        (api_user_exists, api_user_active, _) = api.check_user(email)

        if api_user_active and api_user_active:
            api.edit_user(email, active=False)
            logging.info(f"Deactivated user {email} in Mailcow, not found in LDAP")

        filedb.user_set_active_to(email, False)
        logging.info(f"Deactivated user {email} in filedb, not found in LDAP")

    for address in filedb.get_unchecked_aliases():
        (api_alias_exists, api_alias_address, api_alias_goto, api_alias_active) = api.check_alias(address)

        if api_alias_exists and api_alias_active:
            api.delete_alias(address)
            logging.info(f"Deleting Alias {address} in Mailcow, not found in LDAP")

        filedb.alias_set_active_to(address, False)
        logging.info(f"Deactivated Alias {address} in filedb, not found in LDAP")


def apply_config(config_file, config_data):
    if os.path.isfile(config_file):
        with open(config_file) as f:
            old_data = f.read()

        if old_data.strip() == config_data.strip():
            logging.info(f"Config file {config_file} unchanged")
            return False

        backup_index = 1
        backup_file = f"{config_file}.ldap_mailcow_bak"
        while os.path.exists(backup_file):
            backup_file = f"{config_file}.ldap_mailcow_bak.{backup_index}"
            backup_index += 1

        os.rename(config_file, backup_file)
        logging.info(f"Backed up {config_file} to {backup_file}")

    Path(os.path.dirname(config_file)).mkdir(parents=True, exist_ok=True)

    print(config_data, file=open(config_file, 'w'))

    logging.info(f"Saved generated config file to {config_file}")
    return True


def read_config():
    required_config_keys = [
        'LDAP_MAILCOW_LDAP_URI',
        'LDAP_MAILCOW_LDAP_GC_URI',
        'LDAP_MAILCOW_LDAP_DOMAIN',
        'LDAP_MAILCOW_LDAP_BASE_DN',
        'LDAP_MAILCOW_LDAP_BIND_DN',
        'LDAP_MAILCOW_LDAP_BIND_DN_PASSWORD',
        'LDAP_MAILCOW_API_HOST',
        'LDAP_MAILCOW_API_KEY',
        'LDAP_MAILCOW_API_QUOTA',
        'LDAP_MAILCOW_SYNC_INTERVAL'
    ]

    global config

    for config_key in required_config_keys:
        if config_key not in os.environ:
            sys.exit(f"Required environment value {config_key} is not set")

        config[config_key.replace('LDAP_MAILCOW_', '')] = os.environ[config_key]

    if 'LDAP_MAILCOW_LDAP_FILTER' in os.environ and 'LDAP_MAILCOW_SOGO_LDAP_FILTER' not in os.environ:
        sys.exit('LDAP_MAILCOW_SOGO_LDAP_FILTER is required when you specify LDAP_MAILCOW_LDAP_FILTER')

    if 'LDAP_MAILCOW_SOGO_LDAP_FILTER' in os.environ and 'LDAP_MAILCOW_LDAP_FILTER' not in os.environ:
        sys.exit('LDAP_MAILCOW_LDAP_FILTER is required when you specify LDAP_MAILCOW_SOGO_LDAP_FILTER')
    
    #if 'LDAP_MAILCOW_LDAP_GROUP_FILTER' in os.environ and 'LDAP_MAILCOW_LDAP_FILTER' not in os.environ:
    #    sys.exit('LDAP_MAILCOW_LDAP_FILTER is required when you specify LDAP_MAILCOW_LDAP_GROUP_FILTER')

    #if 'LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER' in os.environ and 'LDAP_MAILCOW_LDAP_GROUP_FILTER' not in os.environ:
    #    sys.exit('LDAP_MAILCOW_LDAP_GROUP_FILTER is required when you specify LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER')

    config['LDAP_FILTER'] = os.environ[
        'LDAP_MAILCOW_LDAP_FILTER'] if 'LDAP_MAILCOW_LDAP_FILTER' in os.environ else '(&(objectClass=user)(objectCategory=person))'
    config['SOGO_LDAP_FILTER'] = os.environ[
        'LDAP_MAILCOW_SOGO_LDAP_FILTER'] if 'LDAP_MAILCOW_SOGO_LDAP_FILTER' in os.environ else "objectClass='user' AND objectCategory='person'"
    config['LDAP_GROUP_FILTER'] = os.environ[
        'LDAP_MAILCOW_LDAP_GROUP_FILTER'] if 'LDAP_MAILCOW_LDAP_GROUP_FILTER' in os.environ else "(&(objectClass=group)(mail=*))"
    config['LDAP_GROUP_MEMBER_FILTER'] = os.environ[
        'LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER'] if 'LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER' in os.environ else "(&(objectClass=person)(mail=*)(distinguishedName={MEMBER_CN}))"    


def read_dovecot_passdb_conf_template():
    with open('templates/dovecot/ldap/passdb.conf') as f:
        data = Template(f.read())

    return data.substitute(
        ldap_gc_uri=config['LDAP_GC_URI'],
        ldap_domain=config['LDAP_DOMAIN'],
        ldap_base_dn=config['LDAP_BASE_DN'],
        ldap_bind_dn=config['LDAP_BIND_DN'],
        ldap_bind_dn_password=config['LDAP_BIND_DN_PASSWORD']
    )


def read_sogo_plist_ldap_template():
    with open('templates/sogo/plist_ldap') as f:
        data = Template(f.read())

    return data.substitute(
        ldap_uri=config['LDAP_URI'],
        ldap_base_dn=config['LDAP_BASE_DN'],
        ldap_bind_dn=config['LDAP_BIND_DN'],
        ldap_bind_dn_password=config['LDAP_BIND_DN_PASSWORD'],
        sogo_ldap_filter=config['SOGO_LDAP_FILTER']
    )


def read_dovecot_extra_conf():
    with open('templates/dovecot/extra.conf') as f:
        data = f.read()

    return data


if __name__ == '__main__':
    main()
