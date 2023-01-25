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

@get('/')
def landing_page(render_template, user, tr):
  log_referrer()
  if user:
    if user.username:
      return redirect(f'/{user.username}')
    else:
      return redirect(f'/{user.id}')
  return render_template('landing_page.html')

@get('/sitemap.xml')
def sitemap(render_template, user, tr):
  with Session(engine) as session:
    response = render_template('sitemap.xml', users=session.query(User).all())
    response.headers['Content-Type'] = 'text/xml'
    return response

@get('/referrers')
def referrers(render_template, user, tr):
  if not user or not user.admin: return redirect('/')
  with Session(engine) as session:
    return render_template('referrers.html', referrers=session.query(Referrer).order_by(Referrer.count.desc()).all())

@get('/register')
def register(render_template, user, tr):
  if user: return redirect('/')
  return render_template('login.html', register=True)

@post('/register')
def register(redirect, user, tr):
  if user: return redirect('/')
  with Session(engine) as session:
    try:
      [user] = session.query(User).where(User.email == request.form['email'])
      if user.email_verified:
        return redirect('/register', tr['account_already_exists'])
    except:
      user = User(email=request.form['email'], api_key=random_128_bit_string())
      session.add(user)
      session.commit()
    login_code = LoginCode(user_id=user.id, code=random_128_bit_string(), expiry=int(time()+60*60*2))
    session.add(login_code)
    session.commit()
    send_email(request.form['email'], tr['verification_email_subject'], render_template('emails/verification.html', tr=tr, code=login_code.code))
    return redirect('/register', tr['verify_your_email'] % request.form['email'])

@get('/login/<code>')
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

@get('/login')
def login(render_template, user, tr):
  if user: return redirect('/')
  return render_template('login.html')

@post('/login')
def login(redirect, user, tr):
  if user: return redirect('/')
  with Session(engine) as session:
    try:
      [user] = session.query(User).where(User.email == request.form['email'])
    except:
      return redirect('/login', tr['email_not_found'])
    login_code = LoginCode(user_id=user.id, code=random_128_bit_string(), expiry=int(time()+60*60*2))
    session.add(login_code)
    session.commit()
    if user.email_verified:
      send_email(request.form['email'], tr['login_email_subject'], render_template('emails/login.html', tr=tr, code=login_code.code))
      return redirect('/login', tr['login_email_sent'])
    else:
      send_email(request.form['email'], tr['verification_email_subject'], render_template('emails/verification.html', tr=tr, code=login_code.code))
      return redirect('/register', tr['verify_your_email'] % request.form['email'])

@post('/logout')
def logout(redirect, user, tr):
  if not user: return redirect('/')
  response = redirect('/')
  response.set_cookie('api_key', '', expires=0)
  return response

@get('/edit')
def settings(render_template, user, tr):
  if not user: return redirect('/')
  return render_template('edit.html')

@post('/edit')
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
  return render_template('view.html', profile=profile, profile_picture_exists=isfile(f'static/profile_pictures/{user.id}'))

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
