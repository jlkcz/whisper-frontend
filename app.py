import os
import time
import datetime
from pprint import pprint

from flask import Flask, render_template, redirect, flash, url_for
from werkzeug.utils import secure_filename

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from flask_migrate import Migrate

from flask_bootstrap import Bootstrap5

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import StringField, EmailField, SubmitField
from wtforms.validators import DataRequired, Email, URL




app = Flask(__name__)

#SECRET_KEY = os.urandom(32)
SECRET_KEY = "iamsecure"
app.config['SECRET_KEY'] = SECRET_KEY

db = SQLAlchemy()
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
db.init_app(app)
migrate = Migrate(app, db)

boostrap = Bootstrap5(app)

##############################
########  Models #############
##############################


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner = db.Column(db.String, nullable=False)
    file = db.Column(db.String, nullable=True)
    url = db.Column(db.String, nullable=True)
    result = db.Column(db.String, nullable=True)
    subs = db.Column(db.String, nullable=True)
    done = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True),
                           server_default=func.now())
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)



##############################
########  Forms  #############
##############################

class NewTaskForm(FlaskForm):
    owner = EmailField("Email (dostane po skončení přepisu upozornění)", validators=[DataRequired(), Email()])
    file = FileField("Soubory k přepisu", validators=[FileRequired()])
    submit = SubmitField("Odeslat")

class NewURLForm(FlaskForm):
    owner = EmailField("Email (dostane po skončení přepisu upozornění)", validators=[DataRequired(), Email()])
    url = StringField("URL adresa videa k přepisu", validators=[DataRequired(), URL()])
    submit = SubmitField("Odeslat")


##############################
########  Routes #############
##############################

@app.route("/")
def index():
    count = db.session.execute(db.select(func.count()).select_from(Task).where(Task.started_at==None) ).scalar()
    return render_template("index.html", count=count)

@app.route("/results")
def results():
    tasks = db.session.execute(db.select(Task).order_by(Task.created_at.desc())).scalars()
    return render_template("results.html", tasks=tasks)

@app.route("/new-url", methods=["GET","POST"])
def new_url():
    form = NewURLForm()
    if form.validate_on_submit():
        task = Task(owner=form.owner.data, url=form.url.data, done=False)
        db.session.add(task)
        db.session.commit()
        flash("Přepis úspěšně přidán","success")
        return redirect(url_for("index"))
    return render_template("new.html", form=form)


@app.route("/new", methods=["GET","POST"])
def new():
    form = NewTaskForm()
    if form.validate_on_submit():
        f = form.file.data
        filename = secure_filename(f.filename)
        full_path = os.path.join(app.instance_path, 'files', filename)
        if os.path.exists(full_path):
            filename = "{0}_{2}{1}".format(*os.path.splitext(filename), int(time.time()))
            full_path = os.path.join(app.instance_path, 'files', filename)
        f.save(full_path)
        task = Task(owner=form.owner.data, file=filename, done=False)
        db.session.add(task)
        db.session.commit()
        flash("Přepis úspěšně přidán","success")
        return redirect(url_for("index"))
    return render_template("new.html", form=form)

@app.route("/text/<int:id>")
def text(id):
    task = db.get_or_404(Task, id)
    return render_template("result.html", content=task.result, id=task.id, filename=task.file)

@app.route("/result/<int:id>")
def result(id):
    task = db.get_or_404(Task, id)
    return render_template("result.html", content=task.subs, id=task.id, filename=task.file)

@app.route("/logs")
def logs():
    content = "".join(reversed(list(open("instance/app.log"))))
    return render_template("logs.html", content=content)

@app.route("/stats")
def stats():
    tasks = db.session.execute(db.select(Task).where(Task.finished_at != None)).scalars()
    unfinished_tasks = db.session.execute(db.select(Task).where(db.and_(Task.finished_at == None, Task.started_at != None))).scalars().all()
    count = 0
    td_sum = datetime.timedelta()
    for task in tasks:
        count += 1
        difference = task.finished_at - task.created_at
        td_sum += difference
    try:
        avg = td_sum/count
    except DivisionByZero:
        avg = 0
    return render_template("stats.html", count=count, td_sum=td_sum, avg=avg, unfinished=len(unfinished_tasks))
#    return f"{count} jobs for {td_sum}, avg {td_sum/count}"
