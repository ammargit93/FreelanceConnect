import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from pymongo import MongoClient
import bcrypt
from werkzeug.utils import secure_filename
import base64
from utils.utils import convert_lists_to_html
# , save_profile_picture, save_profile_picture_free
from dotenv import load_dotenv

load_dotenv()

# Get the Hugging Face API token
CON = os.getenv("CON_STR")

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

client = MongoClient(CON)
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

# @app.route("/client_uploads/<path:filename>")
# def uploaded_file(filename):
#     return send_from_directory("client_uploads", filename)

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
            "user_type": user_type,
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
        posts = list(posts_collection.find({}))
        for post in posts:
            post["_id"] = str(post["_id"])
            post["Content"] = convert_lists_to_html(post["Content"])
        if user_type == "client":
            return render_template("client/client_dashboard.html", posts=posts)
        elif user_type == "freelancer":
            return render_template("freelancer/freelancer_dashboard.html", posts=posts)
        return redirect(url_for("login"))
    return redirect(url_for("login"))



from bson import ObjectId
from datetime import datetime

@app.route("/home/posts/<postid>/comment", methods=["POST"])
def add_comment(postid):
    if "userid" not in session:
        print("Unauthorized: User not logged in.")
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    data = request.get_json()
    print("Received data:", data)  

    comment_text = data.get("comment")
    user_id = data.get("userId")

    if not comment_text or not user_id:
        print("Invalid request: Missing comment or user ID.")
        return jsonify({"success": False, "message": "Invalid request"}), 400

    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        print("User not found:", user_id)
        return jsonify({"success": False, "message": "User not found"}), 404

    comment = {
        "user_id": user_id,
        "username": user["username"],  
        "comment": comment_text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    print("Comment to be added:", comment)  
    result = posts_collection.update_one(
        {"_id": ObjectId(postid)},
        {"$push": {"Comments": comment}}
    )

    if result.modified_count > 0:
        print("Comment added successfully to post:", postid)
        return jsonify({"success": True, "message": "Comment added successfully"})
    else:
        print("Failed to add comment to post:", postid)
        return jsonify({"success": False, "message": "Failed to add comment"}), 500
    
    

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
            skills_required = request.form.get("skills_required")

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
                "Skills": skills_required.split(',') if skills_required else [],
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
                    print(file_path)
            posts_collection.update_one({"_id": inserted_post.inserted_id}, {"$set": post_data})
            print("Post stored in collection!")
            
            return redirect(url_for("home"))
        return render_template("client/client_dashboard.html")
    return redirect(url_for("login"))

from dotenv import load_dotenv
import PyPDF2
import requests
load_dotenv(override=True)

# 
from flask_cors import CORS
CORS(app, resources={r"/analyze": {"origins": "*"}})

API_KEY = os.getenv("GROQ_TOKEN")  # Ensure this is correctly set
BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

def extract_text_from_pdf(pdf_path):
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
    return text

# Function to chat with Groq API
def chat_with_llama(prompt):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "llama3-8b-8192",  # Adjust the model name if needed
        "messages": [{"role": "user", "content": prompt}]
    }
    
    response = requests.post(BASE_URL, json=data, headers=headers)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return f"Error: {response.status_code} - {response.json()}"


# Function to analyze a resume and recommend improvements based on job requirements
def analyze_resume(resume_text, job_requirements):
    prompt = f"""
    Analyze the following resume and provide recommendations to better match the job requirements:
    - Key skills in the resume
    - Missing skills compared to the job requirements
    - Suggestions for improvement

    Resume:
    {resume_text}

    Job Requirements:
    {job_requirements}
    """
    return chat_with_llama(prompt)


@app.route("/analyze", methods=["POST"])
def analyze():
    if "resume" not in request.files:
        return jsonify({"error": "No resume file uploaded"}), 400
    if "job_requirements" not in request.form:
        return jsonify({"error": "Job requirements not provided"}), 400
    resume_file = request.files["resume"]
    job_requirements = request.form["job_requirements"]

    resume_path = "uploaded_resume.pdf"
    resume_file.save(resume_path)
    resume_text = extract_text_from_pdf(resume_path)
    analysis_result = analyze_resume(resume_text, job_requirements)

    return jsonify({"analysis": analysis_result})


@app.route('/analyze', methods=['GET','POST'])
def resumebot():
    return render_template('resumebot.html')

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '').strip()
    if not query and session['user_type']=='client':
        return render_template('client/client_dashboard.html', posts=list(posts_collection.find({})))
    elif not query and session['user_type']=='freelancer':
        return render_template('freelancer/freelancer_dashboard.html', posts=list(posts_collection.find({})))
    results = posts_collection.find({"Title": {"$regex": query, "$options": "i"}})
    jobs = [{"Title": job["Title"], "Content": job["Content"], "Location": job["Location"], "Budget": job["Budget"]} for job in results]
    if session['user_type']=='client':
        return render_template('client/client_dashboard.html', posts=jobs)
    elif session['user_type']=='freelancer':
        return render_template('freelancer/freelancer_dashboard.html', posts=jobs)



@app.route("/match", methods=["POST"])
def match_post():
    if "userid" not in session or session["user_type"].lower() != "client":
        return jsonify({"message": "Unauthorized"}), 401

    data = request.json
    postid = data.get("postid")

    if not postid:
        return jsonify({"message": "Invalid request"}), 400

    # Fetch client post
    clientpost = posts_collection.find_one({"_id": ObjectId(postid), "user_type": "client"})
    if not clientpost:
        return jsonify({"message": "Post not found"}), 404

    required_skills = set(skill.strip().lower() for skill in clientpost.get("Skills", []))
    if not required_skills:
        return jsonify({"message": "No required skills found"}), 400

    print(f"Required Skills: {required_skills}")

    freelance_posts = list(posts_collection.find({"user_type": "freelancer"}))

    matched_freelancers_list = []
    total_match_percentages = []

    seen_freelancers = set()  # To prevent duplicates

    for fpost in freelance_posts:
        freelancer_skills = set(skill.strip().lower() for skill in fpost.get("Skills_required", []))
        matched_skills = freelancer_skills & required_skills

        if matched_skills:
            freelancer_id = str(fpost["UID"])

            if freelancer_id not in seen_freelancers:  # Prevent duplicates
                seen_freelancers.add(freelancer_id)
                match_percent = round((len(matched_skills) / len(required_skills)) * 100, 2)
                total_match_percentages.append(match_percent)

                freelancer = users_collection.find_one({"_id": ObjectId(freelancer_id)})
                if freelancer:
                    matched_freelancers_list.append({
                        "freelancer_id": freelancer_id,
                        "name": freelancer.get("username", "Unknown"),
                        "email": freelancer.get("email", "None"),
                        "skills": list(freelancer_skills),
                        "match_percent": match_percent  # Include percentage
                    })

    avg_match_percent = round(sum(total_match_percentages) / len(total_match_percentages), 2) if total_match_percentages else 0

    print(f"Matched Freelancers: {matched_freelancers_list}")

    return jsonify({"matched_freelancers": matched_freelancers_list, "avg_match_percent": avg_match_percent})


@app.route("/home/myposts")
def my_posts():
    if "userid" not in session or session["user_type"].lower() != "client":
        return redirect(url_for("login"))
    client_id = session["userid"]
    posts = list(posts_collection.find({"UID": client_id}))
    return render_template("client/myposts.html", posts=posts)



UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["ALLOWED_EXTENSIONS"] = ALLOWED_EXTENSIONS
@app.route("/home/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
@app.route("/home/profile/client/<userid>", methods=["GET", "POST"])
def client_profile(userid):
    if "userid" not in session:
        return redirect(url_for("login"))

    if session['userid'] != userid:
        return redirect(url_for("client_profile", userid=session['userid']))

    client_data = profile_collection.find_one({"uid": userid})
    user = users_collection.find_one({"_id": ObjectId(userid)})  # Ensure ObjectId is used

    if request.method == "POST":
        profile_pic = request.files.get("profile_pic")
        name = request.form.get("name")
        work_experience = request.form.get("work_experience")
        education = request.form.get("education")
        bio = request.form.get("bio")

        update_data = {
            "uid": userid,
            "name": name,
            "work_experience": work_experience,
            "education": education,
            "bio": bio,
            "user_type": session['user_type']
        }

        if profile_pic:
            profile_pic_path = save_profile_picture(profile_pic, userid, session['user_type'])
            if profile_pic_path:
                update_data["profile_pic"] = profile_pic_path  

        if client_data:
            profile_collection.update_one({"uid": userid}, {"$set": update_data})
        else:
            profile_collection.insert_one(update_data)

        users_collection.update_one(
            {"_id": ObjectId(userid)},
            {"$set": {"profile_url": f"localhost:5000/home/profile/client/{userid}"}}
        )
        return redirect(url_for("client_profile", userid=userid))

    client_data = profile_collection.find_one({"uid": userid})
    return render_template("client/profile.html", client=client_data, userid=userid)

# Freelancer Profile Route
@app.route("/home/profile/freelance/<userid>", methods=["GET", "POST"])
def freelancer_profile(userid):
    if "userid" not in session:
        return redirect(url_for("login"))
    
    if session['userid'] != userid:
        return redirect(url_for("freelancer_profile", userid=session['userid']))  
    
    client_data = profile_collection.find_one({"uid": userid})
    print(userid)

    if request.method == "POST":
        profile_pic = request.files.get("profile_pic")
        resume = request.files.get("resume")  # Get resume file
        name = request.form.get("name")
        work_experience = request.form.get("work_experience")
        education = request.form.get("education")
        bio = request.form.get("bio")
        hobbies = request.form.get("hobbies")

        update_data = {
            "uid": userid,
            "name": name,
            "work_experience": work_experience,
            "education": education,
            "bio": bio,
            "hobbies": hobbies
        }

        if profile_pic:
            profile_pic_path = save_profile_picture(profile_pic, userid, session['user_type'])
            if profile_pic_path:
                update_data["profile_pic"] = profile_pic_path

        # Handle Resume File
        upload_dir = f"freelance_uploads/{userid}"
        os.makedirs(upload_dir, exist_ok=True)

        files = glob.glob(os.path.join(upload_dir, '*'))
        for file in files:
            if os.path.isfile(file):
                os.remove(file)

        if resume:
            resume_path = os.path.join(upload_dir, resume.filename)
            resume.save(resume_path)
            update_data["resume"] = resume_path

        print(f"Profile picture path: {profile_pic_path if profile_pic else 'No change'}")
        print(f"Resume saved at: {resume_path if resume else 'No change'}")

        # Update or insert profile data
        if client_data:
            profile_collection.update_one({"uid": userid}, {"$set": update_data})
        else:
            profile_collection.insert_one(update_data)
            curruser = users_collection.find_one({"uid": userid})
            if curruser:
                users_collection.update_one(
                    {"uid": userid},
                    {"$set": {"profile_url": f"localhost:5000/home/profile/freelance/{userid}"}}
                )

        return redirect(url_for("freelancer_profile", userid=userid))  

    client_data = profile_collection.find_one({"uid": userid})
    print(f"Client data: {client_data}")
    return render_template("freelancer/profile.html", client=client_data, userid=userid)

# Helper Functions
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]

def save_profile_picture(profile_pic, userid, user_type):
    try:
        if user_type == "client":
            upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], "clientpfp")
        else:
            upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], "freelancepfp")
        os.makedirs(upload_folder, exist_ok=True)
        for filename in os.listdir(upload_folder):
            if filename.startswith(f"profile_{userid}"):
                file_path = os.path.join(upload_folder, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)

        # Save the new profile picture
        if not allowed_file(profile_pic.filename):
            return None
        file_ext = os.path.splitext(profile_pic.filename)[1].lower()
        filename = f"profile_{userid}{file_ext}"
        save_path = os.path.join(upload_folder, filename)
        profile_pic.save(save_path)

        # Return the relative path
        return os.path.relpath(save_path, app.config['UPLOAD_FOLDER'])
    except Exception as e:
        print(f"Error saving profile picture: {e}")
        return None


FREE_UPLOAD_FOLDER = "freelance_uploads"
from flask import Flask, request, redirect, url_for, render_template, jsonify
from werkzeug.utils import secure_filename
import os
from bson import json_util

@app.route("/home/freelanceposts", methods=["GET", "POST"])
def freelance_posts():
    print("Request method:", request.method)
    
    if "userid" in session and session["user_type"].lower() == "freelancer":
        if request.method == "POST":
            
            title = request.form.get("title")
            description = request.form.get("description")
            category = request.form.get("category")
            location = request.form.get("location")
            budget = request.form.get("budget")
            delivery_time = request.form.get("delivery_time")
            skills_required = request.form.get("skills_required")
            documents = request.files.getlist("documents")
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

       
        posts = list(posts_collection.find({}))  # Show all posts

        return render_template("freelancer/freelancer_dashboard.html", posts=posts)
   
    return redirect(url_for("login"))




@app.route("/home/clients")
def client_chatroom():
    if "userid" not in session:
        return redirect(url_for("login"))
    clients = users_collection.find({"user_type": "client"}) 
    return render_template("freelancer/clients.html", clients=clients)




@app.route("/home/chatroom")
def home_clients():
    if "userid" not in session:
        return redirect(url_for("login"))
    user = users_collection.find_one({"_id": ObjectId(session["userid"]), "user_type":"client"})
    if user and "chatrooms" in user:
        chatrooms = user["chatrooms"]
    else:
        chatrooms = []

    return render_template("client/chatroom.html", chatrooms=chatrooms)



from flask import Flask, render_template, session, request, redirect, url_for
from flask_socketio import SocketIO, send, emit, join_room, leave_room

socketio = SocketIO(app)


chatroom_collection = db['chatroom']
@app.route("/start_chat", methods=["POST"])
def start_chat():
    if "userid" in session:
        freelancer_id = session["userid"]  # ID of the freelancer
        client = users_collection.find_one({"username":request.form.get("other_user_id")})
        print(client)
        client_id = str(client.get("_id")) # ID of the client

        print(f"Freelancer ID: {freelancer_id}, Client ID: {client_id}")  # Debugging line

        if freelancer_id == client_id:
            return "Error: Freelancer and client cannot be the same user!", 400  # Prevent self-chat

        room_id = str(ObjectId())  # Generate a unique room ID
        session["room_id"] = room_id
        session["other_user_id"] = client_id

        users_collection.update_one(
            {"_id": ObjectId(freelancer_id)},
            {"$addToSet": {"chatrooms": room_id}}  
        )
        users_collection.update_one(
            {"_id": ObjectId(client_id)},
            {"$addToSet": {"chatrooms": room_id}}  
        )

        # Initialize the chatroom in the collection
        chatroom_collection.insert_one({
            "room_id": room_id,
            "client_id": client_id,
            "freelancer_id": freelancer_id,
            "client_msg": [],
            "freelancer_msg": []
        })

        return redirect(url_for("chat", room_id=room_id))
    return redirect(url_for("login"))

@app.route("/chat/<room_id>")
def chat(room_id):
    if "userid" in session:
        session["room_id"] = room_id
        return render_template("chat.html", room_id=room_id)
    return redirect(url_for("login"))

@socketio.on("join")
def handle_join(data):
    room = data["room"]
    join_room(room)
    send(f"{session.get('username')} has joined the chat.", to=room)

@socketio.on("message")
def handle_message(data):
    room = data["room"]
    message = data["message"]
    sender = session.get("username")
    timestamp = datetime.now().strftime("%H:%M")
    
    # Store message in the chatroom collection under the correct room
    if room:
        chatroom = chatroom_collection.find_one({"room_id": room})
        if chatroom:
            if sender == session.get("username"):  # Check if message sender is the logged in user
                if sender == chatroom["freelancer_id"]:
                    # Save message to freelancer's message array
                    chatroom_collection.update_one(
                        {"room_id": room},
                        {"$push": {"freelancer_msg": {"sender": sender, "message": message, "timestamp": timestamp}}}
                    )
                else:
                    # Save message to client's message array
                    chatroom_collection.update_one(
                        {"room_id": room},
                        {"$push": {"client_msg": {"sender": sender, "message": message, "timestamp": timestamp}}}
                    )
            else:
                # Assuming the other user is the client
                if sender == chatroom["freelancer_id"]:
                    chatroom_collection.update_one(
                        {"room_id": room},
                        {"$push": {"freelancer_msg": {"sender": sender, "message": message, "timestamp": timestamp}}}
                    )
                else:
                    chatroom_collection.update_one(
                        {"room_id": room},
                        {"$push": {"client_msg": {"sender": sender, "message": message, "timestamp": timestamp}}}
                    )

            emit("message", {"sender": sender, "message": message, "timestamp": timestamp}, to=room)

@socketio.on("leave")
def handle_leave(data):
    room = data["room"]
    leave_room(room)
    send(f"{session.get('username')} has left the chat.", to=room)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landingpage"))

if __name__ == "__main__":
    app.run(debug=True)
    socketio.run(app, debug=True)