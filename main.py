import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from pymongo import MongoClient
import bcrypt
from werkzeug.utils import secure_filename
import base64
from utils.utils import convert_lists_to_html, save_profile_picture

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

client = MongoClient("mongodb://localhost:27017/")
db = client["freelanceconnect"]
users_collection = db["users"]
posts_collection = db["posts"]
file_collection = db['files']
profile_collection = db['profile']


UPLOAD_FOLDER = "client_uploads"
ALLOWED_EXTENSIONS = {"pdf", "jpg", "png", "docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["FREE_UPLOAD_FOLDER"] = "freelance_uploads"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def landingpage():
    return render_template("landingpage.html")
from flask import send_from_directory

@app.route("/client_uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory("client_uploads", filename)

@app.route("/auth/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        data = request.form
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")
        user_type = data.get("user_type")

        if users_collection.find_one({"email": email}):
            return jsonify({"message": "User already exists"}), 400

        hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        users_collection.insert_one({
            "username": username,
            "email": email,
            "hashed_password": hashed_pw,
            "user_type": user_type
        })
        return redirect(url_for("login"))
    return render_template("signup.html")


@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.form
        username = data.get("username")
        password = data.get("password")

        user = users_collection.find_one({"username": username})

        if user and bcrypt.checkpw(password.encode("utf-8"), user["hashed_password"]):
            session["username"] = user["username"]
            session["user_type"] = user["user_type"]
            session["email"] = user["email"]
            session["userid"] = str(user["_id"])
            return redirect(url_for("home"))

        return jsonify({"message": "Invalid credentials"}), 401

    return render_template("login.html")

@app.route("/home", methods=["GET", "POST"])
def home():
    if "userid" in session:
        user_type = session.get("user_type", "").lower()
        
        search_query = request.args.get("search", "").strip().lower()
        min_budget = request.args.get("min_budget", "")
        max_budget = request.args.get("max_budget", "")
        location_filter = request.args.get("location", "").strip().lower()

        filter_criteria = {}

        if search_query:
            filter_criteria["Title"] = {"$regex": search_query, "$options": "i"}  # Case-insensitive search
        
        if location_filter:
            filter_criteria["Location"] = {"$regex": location_filter, "$options": "i"}
        
        if min_budget.isdigit():
            filter_criteria["Budget"] = {"$gte": int(min_budget)}

        if max_budget.isdigit():
            if "Budget" in filter_criteria:
                filter_criteria["Budget"]["$lte"] = int(max_budget)
            else:
                filter_criteria["Budget"] = {"$lte": int(max_budget)}

        posts = list(posts_collection.find(filter_criteria))

        for post in posts:
            post["_id"] = str(post["_id"])
            post["Content"] = convert_lists_to_html(post["Content"])

        if user_type == "client":
            return render_template("client/client_dashboard.html", posts=posts)
        elif user_type == "freelancer":
            return render_template("freelancer/freelancer_dashboard.html", posts=posts)
        
        return redirect(url_for("login"))
    
    return redirect(url_for("login"))




@app.route("/home/posts", methods=["GET", "POST"])
def posts():
    print("Request method:", request.method)

    if "userid" in session and session["user_type"].lower() == "client":
        if request.method == "POST":
            print("Form submitted!")

            title = request.form.get("title")
            content = request.form.get("description")
            location = request.form.get("location")
            budget = request.form.get("budget")
            documents = request.files.getlist("document")

            print("Title:", title)
            print("Content:", content)
            print("Documents:", [doc.filename for doc in documents] if documents else "No document")
            if not title or not content:
                print("Missing fields!")
                return "Missing title or content", 400
            post_data = {
                "Title": title,
                "Content": content,
                "Location":location,
                "Budget": budget,
                "Multimedia": [],
                "Comments": [],
                "UID": session["userid"],
                "user_type": session["user_type"]
            }
            inserted_post = posts_collection.insert_one(post_data)
            post_id = str(inserted_post.inserted_id)  
            user_folder = os.path.join(app.config["UPLOAD_FOLDER"], f"client_{session['userid']}")
            post_folder = os.path.join(user_folder, "posts", post_id, "multimedia")
            os.makedirs(post_folder, exist_ok=True)  
            for doc in documents:
                if doc and allowed_file(doc.filename):
                    filename = secure_filename(doc.filename)
                    file_path = os.path.join(post_folder, filename)
                    doc.save(file_path)
                    post_data["Multimedia"].append(file_path)  
            posts_collection.update_one({"_id": inserted_post.inserted_id}, {"$set": post_data})
            print("Post stored in collection!")
            return redirect(url_for("home"))
        return render_template("client/client_dashboard.html")
    return redirect(url_for("login"))



@app.route("/home/myposts")
def my_posts():
    if "userid" not in session or session["user_type"].lower() != "client":
        return redirect(url_for("login"))
    client_id = session["userid"]
    posts = list(posts_collection.find({"UID": client_id}))
    return render_template("client/myposts.html", posts=posts)


@app.route("/home/profile/<userid>", methods=["GET", "POST"])
def client_profile(userid):
    if "userid" not in session:
        return redirect(url_for("login"))

    client_data = profile_collection.find_one({"_id": userid})
    print(userid)
    if request.method == "POST":
        profile_pic = request.files.get("profile_pic")
        name = request.form.get("name")
        work_experience = request.form.get("work_experience")
        education = request.form.get("education")
        bio = request.form.get("bio")

        update_data = {
            "uid": userid,  # Ensure document key
            "name": name,
            "work_experience": work_experience,
            "education": education,
            "bio": bio
        }

        if profile_pic:
            profile_pic_path = save_profile_picture(profile_pic, userid)
            if profile_pic_path:
                update_data["profile_pic"] = profile_pic_path
            print(profile_pic_path)

        if client_data:
            profile_collection.update_one({"uid": userid}, {"$set": update_data})
        else:
            profile_collection.insert_one(update_data)
        print(client_data)
        return redirect(url_for("client_profile", userid=userid))
    client_data = profile_collection.find_one({"uid": userid})
    return render_template("client/profile.html", client=client_data, userid=userid)


FREE_UPLOAD_FOLDER = "freelance_uploads"
@app.route("/home/freelanceposts", methods=["GET", "POST"])
def freelance_posts():
    print("Request method:", request.method)
    

    if "userid" in session and session["user_type"].lower() == "freelancer":
        if request.method == "POST":
            print("Form submitted!")
            print(request.form)
            title = request.form.get("title")
            description = request.form.get("description")
            category = request.form.get("category")
            location = request.form.get("location")
            budget = request.form.get("budget")
            delivery_time = request.form.get("delivery_time")
            skills_required = request.form.get("skills_required")
            documents = request.files.getlist("documents")

            # Debugging prints
            print(f"Title: {title}, Description: {description}, Category: {category}, Location: {location}")
            print(f"Budget: {budget}, Delivery Time: {delivery_time}, Skills: {skills_required}")
            print("Documents:", [doc.filename for doc in documents] if documents else "No document")

            # Validation
            if not title or not description or not category or not delivery_time:
                print("Missing required fields!")
                return "Missing required fields", 400

            # Post data dictionary
            post_data = {
                "Title": title,
                "Content": description,
                "Category": category,
                "Location": location,
                "Budget": budget,
                "Delivery_time": delivery_time,
                "Skills_required": skills_required.split(",") if skills_required else [],
                "Multimedia": [],
                "Comments": [],
                "UID": session["userid"],
                "user_type": session["user_type"]
            }

            # Insert post into the collection
            inserted_post = posts_collection.insert_one(post_data)
            post_id = str(inserted_post.inserted_id)

            # Create directories
            user_folder = os.path.join(app.config["FREE_UPLOAD_FOLDER"], f"freelancer_{session['userid']}")
            post_folder = os.path.join(user_folder, "posts", post_id, "multimedia")
            os.makedirs(post_folder, exist_ok=True)

            # Handle file uploads
            for doc in documents:
                if doc and allowed_file(doc.filename):
                    filename = secure_filename(doc.filename)
                    file_path = os.path.join(post_folder, filename)
                    doc.save(file_path)
                    post_data["Multimedia"].append(filename)  
            posts_collection.update_one({"_id": inserted_post.inserted_id}, {"$set": post_data})
            print("Post stored in collection!")
            return redirect(url_for("home"))
        return render_template("freelancer/freelancer_dashboard.html")
    return redirect(url_for("login"))




@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landingpage"))

if __name__ == "__main__":
    app.run(debug=True)
