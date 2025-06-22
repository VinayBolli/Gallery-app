Key Features
- User Authentication via Firebase ID tokens
- Image Upload to Google Cloud Storage (GCS)
- Gallery Management: create, rename, delete galleries
- Duplicate Detection within and across galleries (via image path hashing)
- Gallery Sharing with other users by email
- Fast, responsive frontend using Jinja2 templates and static file serving
- Backend powered by Google Firestore for storing metadata

Technologies Used
- FastAPI
- Firebase Authentication
- Firestore
- Google Cloud Storage
- Jinja2 Templates
- Render.com (or any deployment platform)

How It Works
- On login, Firebase tokens are validated, and the user's Firestore profile is created.
Users can:
- Create personal galleries.
- Upload images to GCS, linked by metadata to Firestore.
- Detect and view duplicate images.
- Share galleries with registered users by email.
- Every image is accessible via a signed or public GCS URL and tied to metadata in Firestore (Images collection).
- Sharing is managed by appending entries to the Users.shared array in Firestore.
