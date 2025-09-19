import datetime
import logging
import os
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker

logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%d.%m.%y %H:%M:%S', level=logging.INFO)

db_file = 'db/ldap-mailcow.sqlite3'
Base = declarative_base()


class DbUser(Base):  # type: ignore
    __tablename__ = 'users'
    email = Column(String, primary_key=True)
    active = Column(Boolean, nullable=False)
    last_seen = Column(DateTime, nullable=False)

class DbAlias(Base):
    __tablename__ = 'aliases'
    address = Column(String, primary_key=True)
    goto = Column(String, nullable=False)
    active = Column(Boolean, nullable=False)
    last_seen = Column(DateTime, nullable=False)    


Session = sessionmaker()

if not os.path.isfile(db_file):
    logging.info(f"New database file created: {db_file}")

db_engine = create_engine(f"sqlite:///{db_file}")  # echo=True
Base.metadata.create_all(db_engine)
Session.configure(bind=db_engine)
session = Session()
session_time = datetime.datetime.now()

def get_unchecked_active_users():
    query = session.query(DbUser.email).filter(DbUser.last_seen != session_time).filter(DbUser.active == True)
    return [x.email for x in query]

def get_unchecked_aliases():
    query = session.query(DbAlias.address).filter(DbAlias.last_seen != session_time).filter(DbAlias.active == True)
    return [x.address for x in query]


def add_alias(address, goto, active=True):
    session.add(DbAlias(address=address, goto=goto, active=active, last_seen=session_time))
    session.commit()
    logging.info(f"[ + ] [fdb] [ Alias ] {address} => {goto} (Active: {active}) - added alias in filedb")

def check_user(email):
    user = session.query(DbUser).filter_by(email=email).first()
    if user is None:
        return False, False
    user.last_seen = session_time
    session.commit()
    return True, user.active

def check_alias(address):
    alias = session.query(DbAlias).filter_by(address=address).first()
    if alias is None:
        return False, False, False
    alias.last_seen = session_time
    session.commit()
    return True, alias.goto, alias.active

def user_set_active_to(email, active):
    user = session.query(DbUser).filter_by(email=email).first()
    user.active = active
    session.commit()
    logging.info(f"{'[ A ]' if active else '[ D ]'} [fdb] [ User  ] {email} - (A)ctiveted/(D)eactivated user in filedb")

def alias_set_active_to(address, active):
    alias = session.query(DbAlias).filter_by(address=address).first()
    alias.active = active
    session.commit()
    logging.info(f"{'[ A ]' if active else '[ D ]'} [fdb] [ Alias ] {address} - (A)ctiveted/(D)eactivated alias in filedb")

def edit_alias_goto(address, goto):
    alias = session.query(DbAlias).filter_by(address=address).first()
    alias.goto = goto
    session.commit()