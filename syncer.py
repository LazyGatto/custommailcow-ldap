import datetime
import logging
import os
import sys
import time

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

    api.api_host = config['API_HOST']
    api.api_key = config['API_KEY']

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

    logging.info("=== Iterate LDAP Users (User Aliases Only) ===")

    ldap_results = ldap_connector.search_s(config['LDAP_BASE_DN'], ldap.SCOPE_SUBTREE,
                                           config['LDAP_FILTER'],
                                           ['mail', 'userAccountControl', 'proxyAddresses'])

    for x in ldap_results:
        try:
            # LDAP Search still returns invalid objects, test instead of throw.
            if not x[0]:
                continue
            email = x[1]['mail'][0].decode()
            ldap_active = False if int(x[1]['userAccountControl'][0].decode()) & 0b10 else True

            # Process user aliases from proxyAddresses
            if "proxyAddresses" in x[1]:
                for a in x[1]['proxyAddresses']:
                    ldap_alias = a.decode().replace("smtp:", "")

                    (db_alias_exists, db_alias_goto, db_alias_active) = filedb.check_alias(ldap_alias)
                    (api_alias_exists, api_alias_address, api_alias_goto, api_alias_active) = api.check_alias(ldap_alias)

                    unchanged = True

                    if not db_alias_exists:
                        filedb.add_alias(ldap_alias, email, ldap_active)
                        (db_alias_exists, db_alias_active) = (True, ldap_active)
                        unchanged = False

                    if not api_alias_exists:
                        api.add_alias(ldap_alias, email)
                        (api_alias_exists, api_alias_goto, api_alias_active) = (True, email, True)
                        unchanged = False

                    if db_alias_active != ldap_active:
                        filedb.alias_set_active_to(ldap_alias, ldap_active)
                        unchanged = False

                    if api_alias_active != ldap_active:
                        api.edit_alias(ldap_alias, email, ldap_active)
                        logging.info(f"{'[ A ]' if ldap_active else '[ D ]'} [API] [ Alias ] {ldap_alias} - (A)ctiveted/(D)eactivated alias in mailcow")
                        unchanged = False
                    
                    if unchanged:
                        logging.info(f"[OK!] [ ~ ] [ Alias ] Checked alias {ldap_alias} => {email}, unchanged...")

        except Exception:
            #DEBUG
            print(traceback.format_exc())
            #DEBUG
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
                unchanged = False

            if not api_alias_exists:
                api.add_alias(alias_address, alias_goto)
                (api_alias_exists, api_alias_goto, api_alias_active) = (True, alias_goto, True)
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
                logging.info(f"[OK!] [ ~ ] [ Alias ] Checked alias {alias_address}, unchanged")

        except Exception:
            #DEBUG
            print(traceback.format_exc())
            #DEBUG
            logging.info(f"Exception during handling of {x}")
            pass            

    if config['DISABLE_DELETED_USERS']:
        logging.info("=== Check for deleted users in LDAP ===")
        for email in filedb.get_unchecked_active_users():
            (api_user_exists, api_user_active) = api.check_user(email)

            if api_user_exists and api_user_active:
                api.edit_user(email, active=False)
                logging.info(f"[ D ] [API] [ User  ] {email} - deactivating user in mailcow, not found in LDAP (you can delete it manually)")

            filedb.user_set_active_to(email, False)
    else:
        logging.info("=== Skipping user deactivation (LDAP_MAILCOW_DISABLE_DELETED_USERS not enabled) ===")

    logging.info("=== Check for deleted aliases in LDAP ===")
    for address in filedb.get_unchecked_aliases():
        (api_alias_exists, api_alias_address, api_alias_goto, api_alias_active) = api.check_alias(address)

        if api_alias_exists:
            api.delete_alias(address)

        filedb.alias_set_active_to(address, False)




def read_config():
    required_config_keys = [
        'LDAP_MAILCOW_LDAP_URI',
        'LDAP_MAILCOW_LDAP_BASE_DN',
        'LDAP_MAILCOW_LDAP_BIND_DN',
        'LDAP_MAILCOW_LDAP_BIND_DN_PASSWORD',
        'LDAP_MAILCOW_API_HOST',
        'LDAP_MAILCOW_API_KEY',
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
    config['LDAP_GROUP_FILTER'] = os.environ[
        'LDAP_MAILCOW_LDAP_GROUP_FILTER'] if 'LDAP_MAILCOW_LDAP_GROUP_FILTER' in os.environ else "(&(objectClass=group)(mail=*))"
    config['LDAP_GROUP_MEMBER_FILTER'] = os.environ[
        'LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER'] if 'LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER' in os.environ else "(&(objectClass=person)(mail=*)(distinguishedName={MEMBER_CN}))"
    config['DISABLE_DELETED_USERS'] = os.environ.get('LDAP_MAILCOW_DISABLE_DELETED_USERS', 'false').lower() == 'true'    




if __name__ == '__main__':
    main()
