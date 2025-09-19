# LDAP_MAILCOW - Alias Synchronization

Synchronizes user and group aliases from LDAP (e.g., Active Directory) with mailcow-dockerized. This tool is designed to work only with aliases and does not create user mailboxes.

* [How it works](#how-it-works)
* [Usage](#usage)
  * [User Aliases](#user-aliases)
  * [Group Aliases](#group-aliases)
  * [Disabling Deleted Users](#disabling-deleted-users)
* [Limitations](#limitations)
* [Customizations and Integration Support](#customizations-and-integration-support)

## How it works

A Python script periodically checks LDAP and creates/updates aliases in mailcow via API:

1. **User aliases**: extracts aliases from the `proxyAddresses` attribute of LDAP users
2. **Group aliases**: creates aliases for LDAP groups, where the group address forwards to all group members
3. **Optionally**: disables users that are no longer found in LDAP (if enabled)

## Usage

1. Create a `data/db` directory. The SQLite database for synchronization will be stored there.
2. Create (or update) your `docker-compose.override.yml` with an additional container:

    ```yaml
    version: '2.1'
    services:

        ldap-mailcow:
            image: 'ghcr.io/lazygatto/custommailcow-ldap:latest'
            network_mode: host
            container_name: mailcowcustomized_ldap-mailcow
            depends_on:
                - nginx-mailcow
            volumes:
                - ./data/ldap:/db:rw
            restart: unless-stopped
            environment:
                - LDAP_MAILCOW_LDAP_URI=ldap(s)://dc.example.local
                - LDAP_MAILCOW_LDAP_BASE_DN=OU=Mail Users,DC=example,DC=local
                - LDAP_MAILCOW_LDAP_BIND_DN=CN=Bind DN,CN=Users,DC=example,DC=local
                - LDAP_MAILCOW_LDAP_BIND_DN_PASSWORD=BindPassword
                - LDAP_MAILCOW_API_HOST=https://mailcow.example.local
                - LDAP_MAILCOW_API_KEY=XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX
                - LDAP_MAILCOW_SYNC_INTERVAL=300
                - LDAP_MAILCOW_LDAP_FILTER=(&(objectClass=user)(objectCategory=person)(memberOf:1.2.840.113556.1.4.1941:=CN=Group,CN=Users,DC=example DC=local))
                - LDAP_MAILCOW_LDAP_GROUP_FILTER=(&(objectClass=group)(mail=*))
                - LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER=(&(objectClass=person)(mail=*)(distinguishedName={MEMBER_CN}))
                - LDAP_MAILCOW_DISABLE_DELETED_USERS=false
    ```

3. Configure environment variables:

    **Required variables:**
    * `LDAP_MAILCOW_LDAP_URI` - LDAP server URI (e.g., Active Directory). Must be reachable from within the container. Format: `protocol://host:port`, for example `ldap://localhost` or `ldaps://secure.domain.org`
    * `LDAP_MAILCOW_LDAP_BASE_DN` - base DN where user accounts can be found
    * `LDAP_MAILCOW_LDAP_BIND_DN` - bind DN of a special LDAP account that will be used to browse for users
    * `LDAP_MAILCOW_LDAP_BIND_DN_PASSWORD` - password for bind DN account
    * `LDAP_MAILCOW_API_HOST` - mailcow API URL. Make sure it's enabled and accessible from within the container for both reads and writes
    * `LDAP_MAILCOW_API_KEY` - mailcow API key (read/write)
    * `LDAP_MAILCOW_SYNC_INTERVAL` - interval in seconds between LDAP synchronizations

    **Optional LDAP filters:**
    * `LDAP_MAILCOW_LDAP_FILTER` - LDAP filter to apply for finding users, defaults to `(&(objectClass=user)(objectCategory=person))`
    * `LDAP_MAILCOW_LDAP_GROUP_FILTER` - LDAP filter to apply for finding groups and creating aliases, defaults to `(&(objectClass=group)(mail=*))`
    * `LDAP_MAILCOW_LDAP_GROUP_MEMBER_FILTER` - LDAP filter to apply for finding group members, defaults to `(&(objectClass=person)(mail=*)(distinguishedName={MEMBER_CN}))`. Keep `{MEMBER_CN}` as it will be replaced during script execution.

    **Optional control variables:**
    * `LDAP_MAILCOW_DISABLE_DELETED_USERS` - enable disabling users deleted from LDAP (defaults to `false`). Set to `true` if you want the script to disable users that are no longer found in LDAP.

4. Start the additional container: `docker compose up -d ldap-mailcow`
5. Check logs `docker compose logs ldap-mailcow` (or `docker compose logs --tail=100 ldap-mailcow` to reduce log output)

### User Aliases

The script supports user aliases that need to be set in Active Directory in the `proxyAddresses` attribute.
Format records like this: `smtp:username@domain.com`
You can add as many aliases as you need for every user.

### Group Aliases

The script automatically creates aliases for LDAP groups:
- The alias address is taken from the group's `mail` attribute
- The alias forwards emails to all group members who have a `mail` attribute
- When the group membership changes, the alias is automatically updated

### Disabling Deleted Users

If the `LDAP_MAILCOW_DISABLE_DELETED_USERS=true` variable is set, the script will disable users in mailcow that are no longer found in LDAP. This is useful if you are not using mailcow's built-in user synchronization.

If the variable is not set or set to `false`, this functionality is disabled, which is suitable for use with mailcow's built-in user synchronization.

## Limitations

### Aliases Only

This tool is designed only for alias synchronization. It does NOT create user mailboxes. Use mailcow's built-in functionality for user synchronization or create them manually.

### One-way Sync

Aliases from your LDAP directory will be added (and deactivated if deleted/disabled) to your mailcow database. Reverse synchronization is not performed, and this is by design.

### Compatibility

This version was written and tested only with Active Directory on a Windows Server 2019 domain controller.
Compatibility with OpenLDAP or other LDAP implementations has not been tested.

## Customizations and Integration Support

The original tool was created by [Programmierus](https://github.com/Programmierus/LDAP_MAILCOW).
This version is a fork of a fork by [rinkp](https://github.com/rinkp/custommailcow-ldap)

If you run your mailcow server behind Nginx Proxy Manager - you can check [this repo](https://github.com/LazyGatto/npm-cert-export) with an additional script to export SSL certificate into mailcow.

**You can always [contact me](mailto:lazygatto@gmail.com) to help you with the integration or for custom modifications on a paid basis. My current hourly rate (ActivityWatch tracked) is $50 with a 3h minimum commitment.**
