from sqlalchemy import Integer, Numeric, Column, String, Text, Boolean, ForeignKey, Date
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
  __tablename__ = 'users'
  id = Column(Integer, primary_key=True)
  name = Column(String, default='')
  username = Column(String, unique=True)
  open = Column(Boolean, default=False)
  api_key = Column(String)
  email = Column(String)
  email_verified = Column(Boolean, default=False)
  admin = Column(Boolean, default=False)
  phone = Column(String, default='')
  summary = Column(Text, default='')
  profession = Column(Text, default='')
  show_email = Column(Boolean, default=False)
  experiences = relationship('Experience', order_by="[desc(Experience.end), desc(Experience.start), desc(Experience.id)]")
  educations = relationship('Education', order_by="[desc(Education.end), desc(Education.start), desc(Education.id)]")
  social_media = relationship('SocialMedia')
  views = relationship('View')

class Experience(Base):
  __tablename__ = 'experiences'
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  name = Column(String, default='')
  position = Column(String, default='')
  url = Column(String, default='')
  description = Column(Text, default='')
  start = Column(Date)
  end = Column(Date)
  skills = relationship('Skill')

class Education(Base):
  __tablename__ = 'educations'
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  institution = Column(String, default='')
  url = Column(String, default='')
  qualification = Column(String, default='')
  gpa = Column(Numeric)
  start = Column(Date)
  end = Column(Date)
  skills = relationship('Skill')

class Skill(Base):
  __tablename__ = 'skills'
  id = Column(Integer, primary_key=True)
  experience_id = Column(Integer, ForeignKey('experiences.id'))
  education_id = Column(Integer, ForeignKey('educations.id'))
  name = Column(String)

class SocialMedia(Base):
  __tablename__ = 'social_media'
  id = Column(Integer, primary_key=True)
  user_id = Column(Integer, ForeignKey('users.id'))
  name = Column(String)
  url = Column(String)

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
