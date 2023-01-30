from flask import Flask, request, redirect, abort, render_template, make_response
from csrf import csrf
from util import random_128_bit_string
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from decimal import Decimal
from config import DATABASE
from db import User, Experience, Education, SocialMedia, LoginCode, Referrer, View, Skill
from time import time
from mail import send_email
from os.path import isfile
from os import system, unlink
from dateutil.relativedelta import relativedelta
from datetime import date
import re

app = Flask(__name__)
engine = create_engine(DATABASE)
get, post = csrf(app, engine)

def make_url(url):
  url = url.strip()
  if not url: return url
  if url.startswith("http://") or url.startswith("https://"):
    return url
  return f'http://{url}'

def convert_date(d):
  if d == '': return None
  month, year = d.split('/')
  return date.fromisoformat(f'{year}-{month}-01')

def convert_gpa(gpa):
  if gpa == '': return None
  return Decimal(gpa)

def add_skills(skills, new_skills):
  ret = skills
  for skill in new_skills:
    if all([s.name.lower() != skill.name.lower() for s in skills]):
      ret.append(skill)
  return ret

@app.template_filter()
def calculate_duration_in_months(experience, tr):
  if not experience.start:
    return ''
  end = experience.end if experience.end else date.today()
  delta = relativedelta(end, experience.start)
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
def render_date(date):
  if not date: return ''
  return '%04d-%02d-%02d' % (date.year, date.month, date.day)

@app.template_filter()
def render_skills(skills):
  return ', '.join([s.name for s in skills])

@get('/')
def landing_page(render_template, user, tr):
  log_referrer()
  with Session(engine) as session:
    return render_template('landing_page.html', profiles=session.query(User).where(User.name != '').order_by(User.id.asc()))

@get('/cv/privacy-policy')
def privacy(render_template, user, tr):
  log_referrer()
  return render_template('privacy_policy.html')

@get('/cv/terms-and-conditions')
def terms(render_template, user, tr):
  log_referrer()
  return render_template('terms.html')

@get('/sitemap.xml')
def sitemap(render_template, user, tr):
  with Session(engine) as session:
    response = render_template('sitemap.xml', users=session.query(User).all())
    response.headers['Content-Type'] = 'text/xml'
    return response

@get('/cv/cordova')
def cordova(render_template, user, tr):
  response = make_response(redirect('/'))
  response.set_cookie('cordova', 'true')
  return response

@get('/cv/cordova/<code>')
def cordova(render_template, user, tr, code):
  if re.search('[^0-9a-zA-Z]', code): abort(400)
  return f'<!doctype html><script>window.location.href="cvnetwork:{code}";</script>'

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
  if not 'terms' in request.form: return redirect('/cv/sign-up', tr['must_agree'])
  with Session(engine) as session:
    try:
      [user] = session.query(User).where(User.email == request.form['email'].strip().lower())
      if user.email_verified:
        return redirect('/cv/sign-up', tr['account_already_exists'])
    except:
      user = User(email=request.form['email'].strip().lower(), api_key=random_128_bit_string())
      session.add(user)
      session.commit()
    login_code = LoginCode(user_id=user.id, code=random_128_bit_string(), expiry=int(time()+60*60*2))
    session.add(login_code)
    session.commit()
    template = 'emails/verification.html' if not 'cordova' in request.cookies else 'emails/cordova_verification.html'
    send_email(user.email, tr['verification_email_subject'], render_template(template, tr=tr, code=login_code.code))
    return redirect('/cv/sign-up', tr['verify_your_email'] % user.email)

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
    if user.username:
      response = make_response(redirect(f'/{user.username}'))
    else:
      response = make_response(redirect(f'/{user.id}'))
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
      [user] = session.query(User).where(User.email == request.form['email'].strip().lower())
    except:
      return redirect('/cv/login', tr['email_not_found'])
    login_code = LoginCode(user_id=user.id, code=random_128_bit_string(), expiry=int(time()+60*60*2))
    session.add(login_code)
    session.commit()
    if user.email_verified:
      template = 'emails/login.html' if not 'cordova' in request.cookies else 'emails/cordova_login.html'
      send_email(user.email, tr['login_email_subject'], render_template(template, tr=tr, code=login_code.code))
      return redirect('/cv/login', tr['login_email_sent'])
    else:
      template = 'emails/verification.html' if not 'cordova' in request.cookies else 'emails/cordova_verification.html'
      send_email(user.email, tr['verification_email_subject'], render_template(template, tr=tr, code=login_code.code))
      return redirect('/cv/sign-up', tr['verify_your_email'] % request.form['email'])

@post('/cv/logout')
def logout(redirect, user, tr):
  if not user: return redirect('/')
  response = redirect('/')
  response.set_cookie('api_key', '', expires=0)
  return response

@post('/cv/set-username')
def set_username(redirect, user, tr):
  if not user: return redirect('/')
  if re.search('[^a-z0-9-]', request.form['username']) or not re.search('[a-z]', request.form['username']):
    abort(400)
  if len(request.form['username']) > 30:
    abort(400)
  with Session(engine) as session:
    [user] = session.query(User).where(User.id == user.id)
    try:
      if request.form['username'] == 'cv':
        raise Exception
      user.username = request.form['username'] or None
      session.commit()
      return redirect('/cv/edit-basic-info', tr['successful_claim'] + request.form['username'])
    except:
      return redirect('/cv/edit-basic-info', request.form['username'] + tr['is_taken'])

@post('/cv/set-profile-picture')
def set_profile_picture(redirect, user, tr):
  if not user: return abort(403)
  temp = random_128_bit_string()
  request.files['image'].save(f'static/profile_pictures/{temp}')
  system(f"convert static/profile_pictures/{temp} -resize 128x128 static/profile_pictures/{user.id}.png")
  unlink(f'static/profile_pictures/{temp}')
  return {'result': 'success'}

@get('/cv/edit-basic-info')
def edit_basic_info(render_template, user, tr):
  if not user: return redirect('/')
  return render_template('edit_basic_info.html', profile_picture_exists=isfile(f'static/profile_pictures/{user.id}.png'))

@post('/cv/edit-basic-info')
def edit_basic_info(redirect, user, tr):
  if not user: return redirect('/')
  if len(request.form['name']) > 80: abort(400)
  if len(request.form['profession']) > 80: abort(400)
  if len(request.form['phone']) > 80: abort(400)
  if len(request.form['summary']) > 1000: abort(400)
  with Session(engine) as session:
    [user] = session.query(User).where(User.id == user.id)
    user.name = request.form['name']
    user.profession = request.form['profession']
    user.phone = request.form['phone']
    user.summary = request.form['summary']
    user.show_email = 'show_email' in request.form
    user.open = 'open' in request.form
    session.commit()
    if user.username:
      return redirect(f'/{user.username}')
    return redirect(f'/{user.id}')

@get('/cv/experience/<id>')
def experience(render_template, user, tr, id):
  if not user: return redirect('/')
  with Session(engine) as session:
    if id == 'new':
      experience = Experience()
      experience.name = ''
      experience.url = ''
      experience.position = ''
      experience.description = ''
    else:
      try:
        [experience] = session.query(Experience).where(Experience.id == id)
      except:
        abort(404)
      if experience.user_id != user.id:
        abort(403)
    return render_template('experience.html', experience=experience)

@post('/cv/experience/<id>')
def experience(redirect, user, tr, id):
  if not user: return redirect('/')
  if len(request.form['name']) > 80: abort(400)
  if len(request.form['position']) > 80: abort(400)
  if len(request.form['url']) > 80: abort(400)
  if len(request.form['description']) > 1000: abort(400)
  if len(request.form['skills']) > 1000: abort(400)
  try:
    start = convert_date(request.form['start'])
    end = convert_date(request.form['end'])
  except:
    print("aborting")
    abort(400)
  with Session(engine) as session:
    if id == 'new':
      experience = Experience(user_id=user.id, name=request.form['name'], position=request.form['position'], url=make_url(request.form['url']), description=request.form['description'], start=start, end=end)
      session.add(experience)
      session.commit()
      for skill_name in request.form['skills'].split(","):
        if skill_name.strip():
          session.add(Skill(experience_id=experience.id, name=skill_name.strip()))
      session.commit()
    else:
      try:
        [experience] = session.query(Experience).where(Experience.id == id)
      except:
        abort(404)
      if experience.user_id != user.id:
        abort(403)
      experience.name = request.form['name']
      experience.position = request.form['position']
      experience.url = request.form['url']
      experience.description = request.form['description']
      experience.start = start
      experience.end = end
      for skill in experience.skills:
        session.delete(skill)
      for skill_name in request.form['skills'].split(","):
        if skill_name.strip():
          session.add(Skill(experience_id=experience.id, name=skill_name.strip()))
      session.commit()
    if user.username:
      return redirect(f'/{user.username}')
    return redirect(f'/{user.id}')

@post('/cv/experience/delete/<id>')
def experience(redirect, user, tr, id):
  if not user: return redirect('/')
  if id != 'new':
    with Session(engine) as session:
      try:
        [experience] = session.query(Experience).where(Experience.id == id)
      except:
        abort(404)
      if experience.user_id != user.id:
        abort(403)
      for skill in experience.skills:
        session.delete(skill)
      session.delete(experience)
      session.commit()
  if user.username:
    return redirect(f'/{user.username}')
  return redirect(f'/{user.id}')

@get('/cv/education/<id>')
def education(render_template, user, tr, id):
  if not user: return redirect('/')
  with Session(engine) as session:
    if id == 'new':
      education = Education()
      education.institution = ''
      education.url = ''
      education.qualification = ''
    else:
      try:
        [education] = session.query(Education).where(Education.id == id)
      except:
        abort(404)
      if education.user_id != user.id:
        abort(403)
    return render_template('education.html', education=education)

@post('/cv/education/<id>')
def education(redirect, user, tr, id):
  if not user: return redirect('/')
  if len(request.form['institution']) > 80: abort(400)
  if len(request.form['url']) > 80: abort(400)
  if len(request.form['qualification']) > 80: abort(400)
  if len(request.form['skills']) > 1000: abort(400)
  try:
    start = convert_date(request.form['start'])
    end = convert_date(request.form['end'])
    gpa = convert_gpa(request.form['gpa'])
  except:
    abort(400)
  with Session(engine) as session:
    if id == 'new':
      education = Education(user_id=user.id, institution=request.form['institution'], url=make_url(request.form['url']), qualification=request.form['qualification'], gpa=gpa, start=start, end=end)
      session.add(education)
      session.commit()
      for skill_name in request.form['skills'].split(","):
        if skill_name.strip():
          session.add(Skill(education_id=education.id, name=skill_name.strip()))
      session.commit()
    else:
      try:
        [education] = session.query(Education).where(Education.id == id)
      except:
        abort(404)
      if education.user_id != user.id:
        abort(403)
      education.institution = request.form['institution']
      education.url = request.form['url']
      education.qualification = request.form['qualification']
      education.gpa = gpa
      education.start = start
      education.end = end
      for skill in education.skills:
        session.delete(skill)
      for skill_name in request.form['skills'].split(","):
        if skill_name.strip():
          session.add(Skill(education_id=education.id, name=skill_name.strip()))
      session.commit()
    if user.username:
      return redirect(f'/{user.username}')
    return redirect(f'/{user.id}')

@post('/cv/education/delete/<id>')
def education(redirect, user, tr, id):
  if not user: return redirect('/')
  if id != 'new':
    with Session(engine) as session:
      try:
        [education] = session.query(Education).where(Education.id == id)
      except:
        abort(404)
      if education.user_id != user.id:
        abort(403)
      for skill in education.skills:
        session.delete(skill)
      session.delete(education)
      session.commit()
  if user.username:
    return redirect(f'/{user.username}')
  return redirect(f'/{user.id}')

@get('/cv/social-media')
def social_media(render_template, user, tr):
  if not user: return redirect('/')
  with Session(engine) as session:
    [user] = session.query(User).where(User.id == user.id)
    return render_template('social_media.html', user=user)

@post('/cv/social-media')
def social_media(redirect, user, tr):
  if not user: return redirect('/')
  for name, url in zip(*[request.form.getlist(name) for name in ['name', 'url']]):
    if len(name) > 80: abort(400)
    if len(url) > 80: abort(400)
  with Session(engine) as session:
    [user] = session.query(User).where(User.id == user.id)
    for social_media in user.social_media:
      session.delete(social_media)
    for name, url in zip(*[request.form.getlist(name) for name in ['name', 'url']]):
      session.add(SocialMedia(user_id=user.id, name=name, url=url))
    session.commit()
    if user.username:
      return redirect(f'/{user.username}')
    return redirect(f'/{user.id}')

@get('/cv/delete')
def delete(render_template, user, tr):
  if not user: return redirect('/')
  return render_template('delete.html')

@post('/cv/delete')
def delete(redirect, user, tr):
  if not user: return redirect('/')
  with Session(engine) as session:
    [user] = session.query(User).where(User.id == user.id)
    for experience in user.experiences:
      for skill in experience.skills:
        session.delete(skill)
      session.delete(experience)
    for education in user.educations:
      for skill in education.skills:
        session.delete(skill)
      session.delete(education)
    for social_media in user.social_media:
      session.delete(social_media)
    for view in user.views:
      session.delete(view)
    session.delete(user)
    session.commit()
    return redirect('/')

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
  skills = []
  for experience in profile.experiences:
    skills = add_skills(skills, experience.skills)
  for education in profile.educations:
    skills = add_skills(skills, education.skills)
  return render_template('view.html', profile=profile, skills=skills, profile_picture_exists=isfile(f'static/profile_pictures/{profile.id}.png'), short='short' in request.args)

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
