# Student Attendance Management System (SAMS)

## Project Overview
The Student Attendance Management System (SAMS) is a web-based application developed using Django. It aims to simplify student attendance management and provide a foundation for managing attendance digitally.

## Current Features
- User registration
- User login and logout
- Protected dashboard
- Authentication tests

## Technologies Used
- Python
- Django
- HTML and CSS
- SQLite

## Project Structure
```text
SAMS/
├── .gitignore
├── README.md
└── Implement_User_Login/
    ├── accounts/
    ├── config/
    ├── manage.py
    └── db.sqlite3
```

## How to Run the Project

1. Open a terminal in the project folder.
2. Activate your virtual environment.
3. Navigate to the Django project directory:

   ```powershell
   cd Implement_User_Login
   ```

4. Apply database migrations:

   ```powershell
   python manage.py migrate
   ```

5. Start the development server:

   ```powershell
   python manage.py runserver
   ```

6. Open http://127.0.0.1:8000/ in your browser.

## Testing

Run the tests using:

```powershell
python manage.py test
```

## Project Status
The user authentication module is implemented. Additional attendance management features can be added as development continues.
