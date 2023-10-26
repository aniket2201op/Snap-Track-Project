# Store this code in 'app.py' file
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
import MySQLdb.cursors
import re
import cv2
import pytesseract
import numpy as np
import pandas as pd
from datetime import datetime, timedelta




# Placeholder for loaded Excel data
excel_data = None

def load_excel(file_path):
    # Load Excel data using pandas
    return pd.read_excel(file_path)

ALLOWED_EXTENSIONS = set(['png','jpg','jpeg','gif','tiff','tif'])
sheet_ext = set(['xlsx', 'xls',])

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.permanent_session_lifetime = timedelta(days=1)

pytesseract.pytesseract.tesseract_cmd = "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

def is_user_logged_in():
    return 'loggedin' in session

def loggedin_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not is_user_logged_in():
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return decorated_view

def extract_roll_numbers(image_path):
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(blur,0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8)
    dilated = cv2.dilate(binary, kernel, iterations=2)
    hImg, wImg = dilated.shape
    cong = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789,'
    text = pytesseract.image_to_string(dilated, config=cong)
    return [roll.strip() for roll in text.replace('\n', ',').split(',')]

def save_to_excel(attendance_data, date, filename):
    excel_path = f"static/upload_sheet/{filename}.xlsx"

    if not os.path.exists(excel_path):
        # Create a DataFrame with roll numbers from 1 to 100
        df = pd.DataFrame({'Roll Number': range(1, 101)})
        df[date] = 'A'  # Initially mark all students as absent
    else:
        df = pd.read_excel(excel_path)

    if date not in df.columns:
        df[date] = 'A'  # Initially mark all students as absent

    for roll_number in attendance_data['Roll Number']:
        # Update the existing row for the roll number
        df.loc[df[df['Roll Number'] == roll_number].index, date] = 'P'  # Present

    # Sort the columns by date, keeping 'Roll Number' fixed
    cols = ['Roll Number'] + sorted(df.columns.drop('Roll Number'), key=pd.to_datetime)
    df = df[cols]

    df.to_excel(excel_path, index=False)

def allowed_img(filename):
	return '.' in filename and \
			filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_sheet(filename):
	return '.' in filename and \
			filename.rsplit('.', 1)[1].lower() in sheet_ext


app.secret_key = '1234'
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '1234',
    'database': 'ved'
}
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '1234'
app.config['MYSQL_DB'] = 'ved'

mysql = MySQL(app)

@app.route('/')
@app.route('/login', methods =['GET', 'POST'])
def login():
	msg = ''
	if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
		email = request.form['username']
		password = request.form['password']
		cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
		cursor.execute('SELECT * FROM register WHERE email = % s AND password = % s', (email, password, ))
		account = cursor.fetchone()
		if account:
			session['loggedin'] = True
			session['id'] = account['id']
			session['username'] = account['username']
			msg = 'Logged in successfully !'
			return render_template('home.html')
		else:
			msg = 'Incorrect E-mail / password !'
	return render_template('login.html', msg = msg)




@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ''

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        branch = request.form['branch']
        year = request.form['year']
        subject = request.form['subject']
        sem = request.form['sem']  # Added line

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM register WHERE username = %s', (username,))
        account = cursor.fetchone()

        if account:
            msg = 'Account already exists!'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            msg = 'Invalid email address!'
        elif not re.match(r'[A-Za-z0-9]+', username):
            msg = 'Username must contain only characters and numbers!'
        elif not username or not password or not email:
            msg = 'Please fill out the form!'
        else:
            hashed_password = generate_password_hash(password, method='sha256')
            cursor.execute('INSERT INTO register VALUES (NULL, %s, %s, %s, %s, %s, %s, %s)', (username, email, branch, year, subject, hashed_password, sem))
            mysql.connection.commit()
            msg = 'You have successfully registered!'
            return render_template('login.html', msg=msg)

    return render_template('register.html', msg=msg)


@app.route('/home')
def home():
	return render_template('home.html')


@app.route('/download_files/<file_suffix>', methods=['GET'])
def download_files(file_suffix):
    # Logic to get the list of files in a specific folder
    folder_path = 'static/upload_sheet'
    files = [file for file in os.listdir(folder_path) if file.endswith(f'_{file_suffix}')]

    return render_template('your_template.html', files=files, file_suffix=file_suffix)

@app.route('/download_file/<filename>/<file_suffix>', methods=['GET'])
def download_file(filename, file_suffix):
    folder_path = 'static/upload_sheet'
    return send_from_directory(folder_path, filename, as_attachment=True)


# Route to display user profile
@app.route('/user', methods=['GET', 'POST'])
def user_profile():
    global excel_data

    if request.method == 'POST':
        if 'file' in request.files:
            file = request.files['file']

            if file.filename != '':
                file_path = f"{app.config['UPLOAD_FOLDER']}/{file.filename}"
                file.save(file_path)

                # Load Excel data into memory
                excel_data = load_excel(file_path)
                return render_template('user_profile.html', message='File uploaded successfully')

        elif 'prn' in request.form:
            if excel_data is not None:
                prn = int(request.form.get('prn'))  # Convert PRN to int

                # Search for the user with the given PRN
                user = excel_data[excel_data['PRN'] == prn].to_dict(orient='records')

                return render_template('user_profile.html', user=user)

    return render_template('user_profile.html')

@app.route('/attendance', methods=['GET', 'POST'])
@loggedin_required
def attendance():
    try:
        if request.method == 'POST':
            # Check if the post request has the file part
            if 'file' not in request.files:
                raise ValueError('No files selected')

            file = request.files['file']

            # If the user does not select a file, the browser also submits an empty part without filename
            if file.filename == '':
                raise ValueError('No files selected')

            if file and allowed_sheet(file.filename):
                # Specify the folder where you want to save the file
                upload_folder = 'static/upload_sheet'

                # Ensure the folder exists, create it if necessary
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)

                # Save the file to the specified folder
                file.save(os.path.join(upload_folder, file.filename))

                # Additional processing if needed

                return render_template("attendance.html", msg='File uploaded successfully')

    except Exception as e:
        return render_template("attendance.html", error_msg=str(e))

    return render_template('attendance.html')
			

@app.route('/update_profile', methods=['GET', 'POST'])
@loggedin_required
def update_profile():
    msg=''
    data = ''

    if 'loggedin' in session:
        user_id = session['id']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM register WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()

        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'Update':
                # Update user details based on the form data
                
                user_data['branch'] = request.form['branch']
                user_data['year'] = request.form['year']
                user_data['subject'] = request.form['subject']
                user_data['sem'] = request.form['sem']

                # Update the user in the database
                cursor.execute(
                    'UPDATE register SET branch=%s, year=%s, subject=%s, sem=%s WHERE id=%s',
                    (user_data['branch'], user_data['year'],
                     user_data['subject'], user_data['sem'], user_id))
                mysql.connection.commit()
                msg = 'Updated Successfully'

            elif action == 'Delete':
                # Delete user data from the database
                cursor.execute('UPDATE register SET subject=NULL, branch=NULL, year=NULL, sem= NULL WHERE id=%s', (user_id,))
                mysql.connection.commit()
                msg = 'Deleted Successfully'


            elif action == 'Add':
                # Add new data with concatenation
                new_data1 = str(request.form['year'])
                new_data2 = request.form['branch']
                new_data3 = request.form['subject']
                new_data4 = request.form['sem']
                user1 = str(user_data['year'])
                user1 += f', {new_data1}'
                
                user_data['branch'] += f', {new_data2}'  # Modify as needed
                
                user_data['subject'] += f', {new_data3}'

                user_data['sem'] += f', {new_data4}'

                # Update the user in the database
                cursor.execute('UPDATE register SET subject=%s, year=%s, branch=%s, sem=%s WHERE id=%s', (user_data['subject'],user1,user_data['branch'],user_data['sem'], user_id))
                mysql.connection.commit()
                msg = 'Added Successfully'

            cursor.close()
            return render_template('update_profile.html', data= user_data, msg = msg)

        return render_template('update_profile.html', data = user_data, msg=msg)
    else:
        return redirect(url_for('home'))
			

@app.route('/ocr', methods=['GET', 'POST'])
# @loggedin_required
def upload_image():
    user_id =5
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT subject FROM register WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    subjects = user_data['subject'].split(', ') if user_data and 'subject' in user_data else []
    if request.method == 'POST' and 'file' in request.files:
        file = request.files['file']
        if file.filename != '' and file.mimetype.startswith('image'):
            file_path = 'static/uploads/' + file.filename
            file.save(file_path)

            roll_numbers = extract_roll_numbers(file_path)

        return render_template('ocr.html', roll_numbers=roll_numbers, image_path=file_path, data = subjects)

    return render_template('ocr.html')

    

@app.route('/confirm', methods=['POST'])

def confirm_numbers():
    user_id = 5
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT subject FROM register WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    subjects = user_data['subject'].split(', ') if user_data and 'subject' in user_data else []

    confirmed_numbers = request.form.getlist('confirmedNumbers')
    attendance_date = request.form.get('attendance_date')
    filename1 = request.form.get('filename')
    filename1 += f'_{user_id}'
    
    attendance_data = pd.DataFrame({'Roll Number': [int(num) for num in confirmed_numbers]})
    save_to_excel(attendance_data, attendance_date, filename1)
    return render_template('ocr.html', attendance_data=attendance_data, data=subjects)


@app.route('/new_sheet')
@loggedin_required
def render():
	return render_template('attendance.html')

@app.route('/change_password', methods=['GET', 'POST'])
@loggedin_required
def change_password():
    if 'loggedin' in session:
        if request.method == 'POST':
            current_password = request.form['current_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']

            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cursor.execute('SELECT * FROM register WHERE id = %s', (session['id'],))
            user = cursor.fetchone()

            if user and user['password'] == current_password:
                if new_password == confirm_password:
                    try:
                        cursor.execute('UPDATE register SET password = %s WHERE id = %s', (new_password, session['id']))
                        mysql.connection.commit()
                        msg = 'Password updated successfully, Login again'
                        return render_template('login.html', msg=msg)
                    except Exception as e:
                        msg = 'Error updating password: ' + str(e)
                else:
                    msg = 'New password and confirm password do not match'
            else:
                msg = 'Current password is incorrect'
            return render_template('change_pwd.html', msg=msg)
    return render_template('change_pwd.html')



@app.route('/logout')
def logout():
	session.pop('loggedin', None)
	session.pop('id', None)
	session.pop('username', None)
	return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)


