from app import create_app
from extensions import db
from models import User

app = create_app()
with app.app_context():
    # Promote the most recently created user to admin, or ID 1
    user = User.query.filter_by(email="test@example.com").first()
    if not user:
        user = User.query.order_by(User.id.desc()).first()
    
    if user:
        user.role = "admin"
        db.session.commit()
        print(f"User {user.name} ({user.email}) is now an ADMIN!")
    else:
        print("No users found in the database.")
