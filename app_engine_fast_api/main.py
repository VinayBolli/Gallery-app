os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/firebase-creds.json"

from fastapi import FastAPI,Request,Query
from fastapi.responses import HTMLResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.oauth2.id_token
from google.auth.transport import requests
from google.cloud import firestore,storage
from google.cloud.firestore_v1.base_query import FieldFilter
import starlette.status as status
import local_constants
from datetime import datetime
import hashlib
app=FastAPI() 

firestore_db=firestore.Client()

firebase_request_adapter = requests.Request()

app.mount('/static',StaticFiles(directory='static'),name='static')
templates=Jinja2Templates(directory="templates")

def validateFirebaseToken(id_token):
    if not id_token:
        return None
    user_token = None
    try:
        user_token=google.oauth2.id_token.verify_firebase_token(id_token,firebase_request_adapter)   
    except ValueError as err:
        print(str(err))
    return user_token

def getAllGallerynames(user_token: dict):
    if not user_token:
        return []
    
    user_id = user_token.get('user_id')
    if not user_id:
        return []

    galleriesCollection = firestore_db.collection('Galleries')
    galleryQuery = galleriesCollection.where('userLoggedID', '==', user_id).stream()
    print("aaaa",galleryQuery)
    galleries = []
    for gal in galleryQuery:
        galleryData = gal.to_dict()
        gallery_id = galleryData.get('galleryID')
        
        images = firestore_db.collection('Images').where('galleryID', '==', gallery_id).stream()
        image_list = [image.to_dict() for image in images]
        
        if image_list:
            firstImage = min(image_list, key=lambda x: x['uploadedDate'])
            image_path = firstImage['imagePath']
        else:
            image_path = ''
        
        galleries.append({
            'galleryName': galleryData.get('galleryName'),
            'galleryID': gallery_id,
            'imagePath': image_path
        })
    
    return galleries

def getAllSharedGallery(user_token: dict):
    if not user_token:
        return []
    
    user_email = user_token.get('email')
    if not user_email:
        return []

    users_collection = firestore_db.collection('Users')
    sharedGalleries = users_collection.where('userEmail', '==', user_email).stream()

    sharedGalleryId = []
    for user_doc in sharedGalleries:
        shared_data = user_doc.to_dict().get('shared', [])
        print("shared_dataaaaaaaaa",shared_data)
        for entry in shared_data:
            sharedGalleryId.append(entry.get('galleryID'))

    galleries = []
    for galleryId in sharedGalleryId:
        galleryDoc = firestore_db.collection('Galleries').document(galleryId).get()
        if galleryDoc.exists:
            gallery_data = galleryDoc.to_dict()
            galleryName = gallery_data.get('galleryName', 'Unknown Gallery')
            userEmail = gallery_data.get('userEmail', 'Unknown Gallery')
            images = firestore_db.collection('Images').where('galleryID', '==', galleryId).stream()
            image_list = [image.to_dict() for image in images]
            
            if image_list:
                earliest_image = min(image_list, key=lambda x: x['uploadedDate'])
                image_path = earliest_image['imagePath']
            else:
                image_path = ''
            
            galleries.append({
                'galleryName': galleryName,
                'userEmail':userEmail,
                'galleryID': galleryId,
                'imagePath': image_path
            })
    
    return galleries


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    
    if user_token:
        userCollection = firestore_db.collection('Users').document(user_token['user_id'])
        user_doc = userCollection.get()
        if not user_doc.exists:
            userEmail = {
                    "userEmail": user_token["email"]
                }
            userCollection.set(userEmail)

        galleryNames = getAllGallerynames(user_token)
        sharedGalleryNames = getAllSharedGallery(user_token)

        print("sssssssssss",sharedGalleryNames)
        return templates.TemplateResponse('main.html', {'request': request, 'user_token': user_token, 'error_message': None,"galleryNames":galleryNames,"sharedGalleryNames":sharedGalleryNames})

    else:
        return templates.TemplateResponse('main.html', {'request': request, 'user_token': None, 'error_message': None})


@app.get("/addNewGallery", response_class=HTMLResponse)
async def addNewGallery(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    if not user_token:
        print("1")
        return templates.TemplateResponse('main.html', {'request': request, 'user_token': None, 'error_message': None})
    else:
        print("2")
        return templates.TemplateResponse('addNewGallery.html', {'request': request, 'user_token': user_token, 'error_message': ""})


@app.post("/addNewGallery", response_class=RedirectResponse)
async def addNewGallery(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    form = await request.form()

    if user_token:
        new_gallery_name = form["galleryName"].strip().lower()

        user_galleries = firestore_db.collection("Galleries").where("userLoggedID", "==", user_token['user_id']).stream()

        for gallery in user_galleries:
            gallery_data = gallery.to_dict()
            if gallery_data["galleryName"].strip().lower() == new_gallery_name:
                duplicateMsg = "Gallery name already exists"
                return templates.TemplateResponse('addNewGallery.html', {'request': request, 'user_token': user_token, 'error_message': duplicateMsg})

        galleryCollection = firestore_db.collection('Galleries').document()
        getID = galleryCollection.id
        galleryNameObj = {
            "userEmail": user_token["email"],
            "galleryName": form["galleryName"],
            "userLoggedID": user_token['user_id'],
            "galleryID": getID
        }
        galleryCollection.set(galleryNameObj)

        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    else:
        print("User token is invalid")

    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


def getGalNamebyID(galleryID):
    galleryCol = firestore_db.collection("Galleries").document(galleryID)
    document = galleryCol.get()
    
    if document.exists:
        return document.to_dict()
    else:
        return None


@app.get("/editGalName", response_class=HTMLResponse)
async def editGalName(request: Request, galleryID: str = Query(...)):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    # print(galleryID,"galleryID")
    if user_token:
        galleryData = getGalNamebyID(galleryID)
        # print("galleryData",galleryData)
        return templates.TemplateResponse('editGalName.html', {'request': request, 'user_token': user_token, 'error_message': None,"galleryData":galleryData})
    else:
        return templates.TemplateResponse('main.html', {'request': request, 'user_token': None, 'error_message': None})

@app.post("/updateGalleryName", response_class=RedirectResponse)
async def updateGalleryName(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    form = await request.form()
    galleryID = form["galleryID"]
    editedName = form["editedName"].strip().lower()

    if user_token:
        user_galleries = firestore_db.collection("Galleries").where("userLoggedID", "==", user_token['user_id']).stream()

        for gallery in user_galleries:
            gallery_data = gallery.to_dict()
            if gallery_data["galleryName"].strip().lower() == editedName and gallery.id != galleryID:
                duplicateMsg = "Gallery name already exists"
                galleryData = getGalNamebyID(galleryID)  # Fetch the current gallery data to pass to the template
                return templates.TemplateResponse('editGalName.html', {'request': request, 'user_token': user_token, 'galleryData': galleryData, 'duplicateMsg': duplicateMsg})

        galleryCollection = firestore_db.collection('Galleries').document(galleryID)
        galleryNameObj = {
            "galleryName": form["editedName"]
        }
        galleryCollection.update(galleryNameObj)

        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    else:
        print("User token is invalid")

    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

@app.post("/deleteGallery", response_class=RedirectResponse)
async def deleteGallery(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    form = await request.form()

    if user_token:
        try:
            galleryID = form["galleryID"]
            
            images_ref = firestore_db.collection("Images").where("galleryID", "==", galleryID)
            images = images_ref.stream()
            
            for image in images:
                image.reference.delete()
            
            firestore_db.collection("Galleries").document(galleryID).delete()
            
            galleryNames = await getAllGallerynames(user_token)
            return templates.TemplateResponse('main.html', {
                'request': request, 
                'user_token': user_token, 
                'error_message': None, 
                'galleryNames': galleryNames
            })
        
        except Exception as e:
            return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    
    else:
        print("User token is invalid")
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


@app.get("/contentGal", response_class=HTMLResponse)
async def contentGal(request: Request, galleryID: str = Query(...)):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    # print(galleryID)

    if not user_token:
        print("1")
        return templates.TemplateResponse('main.html', {'request': request, 'user_token': None, 'error_message': None})
    else:
        print("2")
        galleryData = getGalNamebyID(galleryID)
        getImageDetailsQuery = firestore_db.collection("Images").where("galleryID", "==", galleryID).get()
        getImageDetails = [doc.to_dict() for doc in getImageDetailsQuery]
        # print(getImageDetails,"getImageDetails")
        return templates.TemplateResponse('contentGal.html', {'request': request, 'user_token': user_token, 'error_message': "",'galleryData':galleryData,'getImageDetails':getImageDetails})


def getImageDetailsbyID(galleryID):
    getImageDetailsQuery = firestore_db.collection("Images").where("galleryID", "==", galleryID)
    documents = getImageDetailsQuery.get()

    image_details = [doc.to_dict() for doc in documents]
    
    return image_details

def getImageDetailsbyUserID(userID):
    # print("galleryID", galleryID)
    getImageDetailsQuery = firestore_db.collection("Images").where("userLoggedID", "==", userID)
    documents = getImageDetailsQuery.get()

    image_details = [doc.to_dict() for doc in documents]
    
    return image_details


@app.post("/imageUpload", response_class=RedirectResponse)
async def imageUpload(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    form = await request.form()
    galImage = form.get("galImage")
    if user_token:
        storage_client = storage.Client(project=local_constants.PROJECT_NAME)
        bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)
        if galImage and galImage.filename:
            addFile(form.get("galImage"))
            filename = form.get("galImage").filename  
            matchingPath = None
            imagePath = []
            blobs = blobList(None)
            for blob in blobs:
                path = f"https://storage.googleapis.com/{local_constants.PROJECT_STORAGE_BUCKET}/{blob.name}"
                imagePath.append(path)

            for path in imagePath:
                if filename in path:
                    matchingPath = path
                    break
        else:
            matchingPath = None    
        user_id = user_token.get("user_id")
        imagesDocRef = firestore_db.collection("Images").document()
        image_data = {
            "userEmail": user_token["email"],
            "userLoggedID": user_id,
            "uploadedDate":datetime.now(),
             "galleryID": form.get("galleryID"),
             "galleryName":form.get("galleryName"),
             "imagePath":matchingPath,
             "imageID":imagesDocRef.id
        }
        imagesDocRef.set(image_data)
        getImageDetails = getImageDetailsbyID(form.get("galleryID"))
        galleryData = getGalNamebyID(form.get("galleryID"))
        return templates.TemplateResponse('contentGal.html', {'request': request, 'user_token': user_token, 'error_message': "",'getImageDetails':getImageDetails,'galleryData':galleryData})

    else:
        print("User token is invalid")
    
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


@app.post("/deleteImage", response_class=RedirectResponse)
async def deleteImage(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    form = await request.form()
    
    if user_token:
            print("test")
            imageID = form["imageID"]
            print("imageID",form.get("galleryID"))
            firestore_db.collection("Images").document(imageID).delete()
            getImageDetails = getImageDetailsbyID(form.get("galleryID"))
            galleryData = getGalNamebyID(form.get("galleryID"))
            return templates.TemplateResponse('contentGal.html', {'request': request, 'user_token': user_token, 'error_message': "",'getImageDetails':getImageDetails,'galleryData':galleryData})
    else:
        print("User token is invalid")
        return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


def findDuplicateImages(imageDetails):
    imageHashMap = {}
    duplicates = []

    for image in imageDetails:
        imageStr = f"{image['imagePath']}"
        imageHash = hashlib.md5(imageStr.encode()).hexdigest()

        if imageHash in imageHashMap:
            if imageHashMap[imageHash] not in duplicates:
                duplicates.append(imageHashMap[imageHash])
            duplicates.append(image)
        else:
            imageHashMap[imageHash] = image

    return duplicates

@app.get("/duplicatewithinGallery", response_class=HTMLResponse)
async def root(request: Request, galleryID: str = Query(...)):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)

    if not user_token:
        return templates.TemplateResponse('main.html', {'request': request, 'user_token': None, 'error_message': None})
    else:
        getImageDetails = getImageDetailsbyID(galleryID)
        galleryData = getGalNamebyID(galleryID)

        duplicates = findDuplicateImages(getImageDetails)

        return templates.TemplateResponse('duplicatewithinGallery.html', {
            'request': request, 
            'user_token': user_token, 
            'error_message': None,
            'duplicates': duplicates,
            'galleryData':galleryData
        })

@app.get("/duplicatesAllGallery", response_class=HTMLResponse)
async def root(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)

    if not user_token:
        return templates.TemplateResponse('main.html', {'request': request, 'user_token': None, 'error_message': None})
    else:
        user_id = user_token.get("user_id")
        getImageDetails = getImageDetailsbyUserID(user_id)
        # galleryData = getGalNamebyID(galleryID)
        print("getImageDetailsqqqqqqqqq",getImageDetails)
        duplicates = findDuplicateImages(getImageDetails)
        print(duplicates,"duplicateseeeeeeeeeeeeeee")
        return templates.TemplateResponse('duplicatesAllGallery.html', {
            'request': request, 
            'user_token': user_token, 
            'error_message': None,
            'duplicates': duplicates
        })


@app.get("/shareGal", response_class=HTMLResponse)
async def root(request: Request, galleryID: str = Query(...)):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)

    if not user_token:
        return templates.TemplateResponse('shareGal.html', {'request': request, 'user_token': None, 'error_message': None})
    else:
        user_id = user_token.get("user_id")
        # getImageDetails = getImageDetailsbyUserID(user_id)
        # galleryData = getGalNamebyID(galleryID) 

        return templates.TemplateResponse('shareGal.html', {
            'request': request, 
            'user_token': user_token, 
            'error_message': " ",
            'galleryID':galleryID
        })

@app.post("/shareGallery", response_class=RedirectResponse)
async def shareGallery(request: Request):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    form = await request.form()

    if user_token:
        user_email = user_token.get("email")
        
        getUsername = firestore_db.collection("Users").where("userEmail", "==", form["Useremail"]).get()
        print("getUsername:", getUsername)
        
        if len(getUsername) == 0:
            duplicateCheck = "Entered email address is not in the system."
            return templates.TemplateResponse('shareGal.html', {'request': request, 'user_token': user_token, 'error_message': duplicateCheck})
        else:
            for doc in getUsername:
                if doc.to_dict().get("userEmail") == form["Useremail"]:
                    imageCollection = firestore_db.collection("Users").document(doc.id)
                    newSharedData = {
                        "sharedEmail": user_email,
                        "galleryID": form["galleryID"]
                    }
                    try:
                        imageCollection.update({
                            "shared": firestore.ArrayUnion([newSharedData])
                        })
                        print("Update.")
                    except Exception as e:
                        print("Error", e)
                    break
            return RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    else:
        print("User token is invalid")

    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

@app.get("/sharedContent", response_class=HTMLResponse)
async def sharedContent(request: Request, galleryID: str = Query(...)):
    id_token = request.cookies.get("token")
    user_token = validateFirebaseToken(id_token)
    # print(galleryID)

    if not user_token:
        print("1")
        return templates.TemplateResponse('main.html', {'request': request, 'user_token': None, 'error_message': None})
    else:
        print("2")
        galleryData = getGalNamebyID(galleryID)
        getImageDetailsQuery = firestore_db.collection("Images").where("galleryID", "==", galleryID).get()
        getImageDetails = [doc.to_dict() for doc in getImageDetailsQuery]
        # print(getImageDetails,"getImageDetails")
        return templates.TemplateResponse('sharedContent.html', {'request': request, 'user_token': user_token, 'error_message': "",'galleryData':galleryData,'getImageDetails':getImageDetails})


def addDirectory(directory_name):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)

    blob = bucket.blob(directory_name)
    blob.upload_from_string('',content_type="application/x-www-form-urlencoded;charset=UTF-8")

def addFile(file):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)
    bucket = storage_client.bucket(local_constants.PROJECT_STORAGE_BUCKET)


    print(file.filename,bucket,"img")
    blob = storage.Blob(file.filename,bucket)
    blob.upload_from_file(file.file)

def blobList(prefix):
    storage_client = storage.Client(project=local_constants.PROJECT_NAME)

    return storage_client.list_blobs(local_constants.PROJECT_STORAGE_BUCKET,prefix=prefix)


