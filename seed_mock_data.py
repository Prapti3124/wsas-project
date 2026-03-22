import os
from app import create_app
from extensions import db
from models import UnsafeZone, CommunityReport, User

app = create_app()

with app.app_context():
    # Only add if empty
    admin = User.query.filter_by(role='admin').first()
    admin_id = admin.id if admin else 1

    if UnsafeZone.query.count() == 0:
        zones = [
            UnsafeZone(name="Isolated Underpass", latitude=19.0760, longitude=72.8777, radius_meters=800, crime_score=85.0, category="High Crime Area"),
            UnsafeZone(name="Deserted Alleyway", latitude=19.0800, longitude=72.8800, radius_meters=500, crime_score=60.0, category="Poor Lighting")
        ]
        db.session.bulk_save_objects(zones)
        print("Fake Unsafe Zones added.")
    
    # Check reports
    if CommunityReport.query.count() == 0:
        reports = [
            CommunityReport(user_id=admin_id, latitude=19.0770, longitude=72.8780, category="harassment", description="Suspicious group loitering.", severity=4),
            CommunityReport(user_id=admin_id, latitude=19.0750, longitude=72.8760, category="lighting", description="Streetlights are broken here.", severity=2)
        ]
        db.session.bulk_save_objects(reports)
        print("Fake Community reports added.")
        
    db.session.commit()
    print("Seeding complete.")
