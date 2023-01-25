from sqlalchemy import Integer, Column, String, Text, Boolean, ForeignKey, Date
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
  __tablename__ = 'users'
  id = Column(Integer, primary_key=True)
  name = Column(String, default='')
  username = Column(String)
  api_key = Column(String)
  email = Column(String)
  email_verified = Column(Boolean, default=False)
  admin = Column(Boolean, default=False)
  experiences = relationship('Experience')
  educations = relationship('Education')
  socials = relationship('Social')

class Experience(Base):
  __tablename__ = 'experiences'
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  name = Column(String)
  url = Column(String)
  description = Column(Text)
  start = Column(Date)
  end = Column(Date)
  skills = relationship('Skill')

class Education(Base):
  __tablename__ = 'educations'
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  institution = Column(String)
  qualification = Column(String)
  start = Column(Date)
  end = Column(Date)

class Social(Base):
  __tablename__ = 'socials'
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  platform = Column(String)
  url = Column(String)
  display_value = Column(String)

class LoginCode(Base):
  __tablename__ = 'login_codes'
  code = Column(String, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  expiry = Column(Integer)
  user = relationship('User')

class Referrer(Base):
  __tablename__ = 'referrers'
  hostname = Column(String, primary_key=True)
  count = Column(Integer)

class View(Base):
  __tablename__ = 'views'
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  remote_address = Column(String)
  timestamp = Column(Integer)
