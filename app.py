from flask import Flask, request, redirect, abort, render_template, make_response
from csrf import csrf
from util import random_128_bit_string
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from config import DATABASE
from db import User, Experience, Education, Social, LoginCode, Referrer, View
from time import time
from mail import send_email
from os.path import isfile
from dateutil.relativedelta import relativedelta
import re

app = Flask(__name__)
engine = create_engine(DATABASE)
get, post = csrf(app, engine)

@app.template_filter()
def calculate_duration_in_months(experience, tr):
  if not experience.start or not experience.end:
    return ''
  delta = relativedelta(experience.end, experience.start)
  delta.months += 1
  if delta.months == 12:
    delta.years += 1
    delta.months = 0
  components = []
  if delta.years == 1:
    components.append(f'1 {tr["year"]}')
  elif delta.years > 1:
    components.append(f'{delta.years} {tr["years"]}')
  if delta.months == 1:
    components.append(f'1 {tr["month"]}')
  elif delta.months > 1:
    components.append(f'{delta.months} {tr["months"]}')
  return f'({" ".join(components)})'

@app.template_filter()
def render_month(date):
  return '%02d/%04d' % (date.month, date.year)

@get('/')
def landing_page(render_template, user, tr):
  log_referrer()
  if user:
    return redirect('/cv/edit')
  return render_template('landing_page.html')

@get('/sitemap.xml')
def sitemap(render_template, user, tr):
  with Session(engine) as session:
    response = render_template('sitemap.xml', users=session.query(User).all())
    response.headers['Content-Type'] = 'text/xml'
    return response

@get('/cv/referrers')
def referrers(render_template, user, tr):
  if not user or not user.admin: return redirect('/')
  with Session(engine) as session:
    return render_template('referrers.html', referrers=session.query(Referrer).order_by(Referrer.count.desc()).all())

@get('/cv/sign-up')
def sign_up(render_template, user, tr):
  if user: return redirect('/')
  return render_template('login.html', sign_up=True)

@post('/cv/sign-up')
def sign_up(redirect, user, tr):
  if user: return redirect('/')
  with Session(engine) as session:
    try:
      [user] = session.query(User).where(User.email == request.form['email'])
      if user.email_verified:
        return redirect('/cv/sign-up', tr['account_already_exists'])
    except:
      user = User(email=request.form['email'], api_key=random_128_bit_string())
      session.add(user)
      session.commit()
    login_code = LoginCode(user_id=user.id, code=random_128_bit_string(), expiry=int(time()+60*60*2))
    session.add(login_code)
    session.commit()
    send_email(request.form['email'], tr['verification_email_subject'], render_template('emails/verification.html', tr=tr, code=login_code.code))
    return redirect('/cv/sign-up', tr['verify_your_email'] % request.form['email'])

@get('/cv/login/<code>')
def login(render_template, user, tr, code):
  with Session(engine) as session:
    try:
      [login_code] = session.query(LoginCode).where(LoginCode.code == code)
    except:
      abort(404)
    if login_code.expiry < time():
      return render_template('login.html', message=tr['login_code_expired'])
    [user] = session.query(User).where(User.id == login_code.user_id)
    user.email_verified = True
    session.delete(login_code)
    session.commit()
    response = make_response(redirect('/'))
    response.set_cookie('api_key', user.api_key)
    return response

@get('/cv/login')
def login(render_template, user, tr):
  if user: return redirect('/')
  return render_template('login.html')

@post('/cv/login')
def login(redirect, user, tr):
  if user: return redirect('/')
  with Session(engine) as session:
    try:
      [user] = session.query(User).where(User.email == request.form['email'])
    except:
      return redirect('/cv/login', tr['email_not_found'])
    login_code = LoginCode(user_id=user.id, code=random_128_bit_string(), expiry=int(time()+60*60*2))
    session.add(login_code)
    session.commit()
    if user.email_verified:
      send_email(request.form['email'], tr['login_email_subject'], render_template('emails/login.html', tr=tr, code=login_code.code))
      return redirect('/cv/login', tr['login_email_sent'])
    else:
      send_email(request.form['email'], tr['verification_email_subject'], render_template('emails/verification.html', tr=tr, code=login_code.code))
      return redirect('/cv/sign-up', tr['verify_your_email'] % request.form['email'])

@post('/cv/logout')
def logout(redirect, user, tr):
  if not user: return redirect('/')
  response = redirect('/')
  response.set_cookie('api_key', '', expires=0)
  return response

@get('/cv/edit')
def edit(render_template, user, tr):
  if not user: return redirect('/')
  with Session(engine) as session:
    [user] = session.query(User).where(User.id == user.id)
    user.experiences
    user.educations
    user.socials
    return render_template('edit.html', user=user)

@post('/cv/set-username')
def set_username(redirect, user, tr):
  if not user: return redirect('/')
  if re.search('[^a-z0-9-]', request.form['username']):
    return {'result': tr['invalid_username']}
  with Session(engine) as session:
    [user] = session.query(User).where(User.id == user.id)
    try:
      user.username = request.form['username']
      session.commit()
      return {'result': tr['successful_claim'] + request.form['username']}
    except:
      return {'result': request.form['username'] + tr['is_taken']}

@post('/cv/edit')
def edit(redirect, user, tr):
  if not user: return redirect('/')
  return "TODO: actually edit the user from the form submitted"

@get('/<int:id>')
def view(render_template, user, tr, id):
  log_referrer()
  with Session(engine) as session:
    try:
      [profile] = session.query(User).where(User.id == id)
    except:
      abort(404)
    return view_profile(render_template, session, profile)

@get('/<username>')
def view(render_template, user, tr, username):
  log_referrer()
  with Session(engine) as session:
    try:
      [profile] = session.query(User).where(User.username == username)
    except:
      abort(404)
    return view_profile(render_template, session, profile)

def view_profile(render_template, session, profile):
  view = session.query(View).filter((View.user_id == profile.id) & (View.remote_address == request.remote_addr)).first()
  if view is None:
    view = View(user_id=profile.id, remote_address=request.remote_addr, timestamp=0)
  if view.timestamp + 60*60*24 < time():
    session.add(View(user_id=profile.id, remote_address=request.remote_addr, timestamp=int(time())))
    session.commit()
  return render_template('view.html', profile=profile, profile_picture_exists=isfile(f'static/profile_pictures/{profile.id}'))

def log_referrer():
  try:
    referrer_hostname = re.match('https?://([^/]*)', request.referrer).group(1)
  except:
    referrer_hostname = 'unknown'
  with Session(engine) as session:
    try:
      [ref] = session.query(Referrer).where(Referrer.hostname == referrer_hostname)
      ref.count += 1
      session.commit()
    except:
      session.add(Referrer(hostname=referrer_hostname, count=1))
      session.commit()
