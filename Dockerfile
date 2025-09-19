FROM python:3-alpine3.14

RUN apk --no-cache add build-base openldap-dev python2-dev python3-dev
RUN pip3 install --upgrade pip
RUN pip3 install python-ldap sqlalchemy requests

COPY api.py filedb.py syncer.py ./

VOLUME [ "/db" ]

ENTRYPOINT [ "python3", "syncer.py" ]