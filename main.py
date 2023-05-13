import socketio
import eventlet
import redis
import json
import time


r = redis.Redis(host='localhost', port=6379, db=0)


'''try:
#     class_id = r.get('class_id').decode('utf-8')
# except Exception as e:
#     print("class_id not found", e)
#     class_id = [{
#         'id': 'blah-blah-blahs',
#         "class_name": "blah-blah-blah",
#         "chatContent": [
#             {
#                 "role": "mentor",
#                 "content": "Hello, I am your class assisten. How can I help you?",
#                 "to_be_sent": "All",
#                 "time": "2021-05-01 12:00:00",
#             },
#             {
#                 "role": "student",
#                 "content": "Hello",
#                 "to_be_sent": "praveensm890@gmail.com",
#                 "time": "2021-05-01 12:01:00"
#             }
#         ],
#         "Mentor": [
#             "praveensm890@gmail.com"
#         ],
#         "Students": [
#             "praveen@guvi.in"
#         ]
#     }
#     ]
#     r.set('blah-blah-blahs', json.dumps(class_id))'''


def insert_chat_content(class_id, chat_content, user_id, email,to_be_sent):
    email = email.replace('%40', '@')
    present = r.get(class_id)
    present = json.loads(present.decode('utf-8'))
    # time in format 2021-05-01 12:00:00
    obj = {
        'role': 'mentor' if email in present[0]['Mentor'] else 'student',
        'content': chat_content,
        'sent_by': email,
        'time': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "to_be_sent": to_be_sent,
    }
    chat_data = present[0]['chatContent']
    chat_data.append(obj)
    present[0]['chatContent'] = chat_data
    r.set(class_id, json.dumps(present))


def get_chat_content(class_id):
    present = r.get(class_id)
    present = json.loads(present.decode('utf-8'))
    if not present:
        return []
    else:
        return present[0]['chatContent']


sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)


@sio.on('connect')
def connect(sid, environ):
    queue_name = environ['QUERY_STRING']
    token = queue_name.split('=')[1].split('&')[0]
    classID = queue_name.split('=')[2].split('&')[0]
    role = queue_name.split('=')[3].split('&')[0]
    email = queue_name.split('=')[4].split('&')[0]
    email = email.replace('%40', '@')
    print(email)
    print("connected", token)
    chatinfo=r.get(classID)
    chatinfo = json.loads(chatinfo.decode('utf-8'))
    if email in chatinfo[0]['Mentor']:
        mentorSid={email:sid}
        for obj in chatinfo[0]["mentorSid"]:
            if email in obj:
                obj[email]=sid
                break
        else:
            chatinfo[0]["mentorSid"].append(mentorSid)
    elif email in chatinfo[0]['Students']:
        studentSid={email:sid}
        for obj in chatinfo[0]["studentSid"]:
            if email in obj:
                obj[email]=sid
                break
        else:
            chatinfo[0]["studentSid"].append(studentSid)
    r.set(classID,json.dumps(chatinfo))
    chat_content = get_chat_content(classID)
    chats = []
    response={}
    if role == "stud":
        for x in chat_content:
            if x['role'] == 'student' and x['sent_by'] == email:
                chats.append(x)
            elif x['role'] == 'mentor' and (x['to_be_sent'] == 'Everyone' or x['to_be_sent'] == email):
                chats.append(x)
        hostsid=[]
        options=[]
        hostsid.append(sid)
        if chatinfo[0]['mentorSid']:
            for s in chatinfo[0]['mentorSid']:
                for key,value in s.items():
                    hostsid.append(value)
                    options.append(key)
        response['chats']=chats
        response['options']=options
        sio.emit('connect',response,to=sid)
    elif role == "ment":
        for x in chat_content:
            if x['role'] == 'mentor' and x['sent_by'] == email:
                chats.append(x)
            elif x['role'] == 'student' and (x['to_be_sent'] == 'All hosts' or x['to_be_sent'] == email):
                chats.append(x)
        options=[]
        for s in chatinfo[0]['studentSid']:
            for key,value in s.items():
                options.append(key)
        response['chats']=chats
        response['options']=options
        sio.emit('connect',response,to=sid)


@sio.on('disconnect')
def disconnect(sid):
    print('Client disconnected:', sid)


@sio.on('chat')
def chat(sid, data):
    #insert the content into the classroom chat
    insert_chat_content(data['classID'], data['chatContent'], data["userID"], data["email"], data['to_be_sent'])
    chats=[]
    chat_content = get_chat_content(data['classID'])
    chatinfo=r.get(data["classID"])
    chatinfo = json.loads(chatinfo.decode('utf-8'))
    #check for the role
    if data['role'] == "stud":
        #get the messages for the student
        for x in chat_content:
            if x['role'] == 'student' and x['sent_by'] == data["email"]:
                chats.append(x)
            elif x['role'] == 'mentor' and (x['to_be_sent'] == 'Everyone' or x['to_be_sent'] == data["email"]):
                chats.append(x)
        if data["to_be_sent"]=="All hosts":
            #check for all the connected hosts
            for s in chatinfo[0]['mentorSid']:
                #for each connected host get their messages and send to them
                for mail,id in s.items():
                    chatm=[]
                    for x in chat_content:
                        if x['role'] == 'mentor' and x['sent_by'] == mail:
                            chatm.append(x)
                        elif x['role'] == 'student' and (x['to_be_sent'] == 'All hosts' or x['to_be_sent'] == mail):
                            chatm.append(x)
                    sio.emit('chat',chatm,to=id)
        else:
            #check to be sent for particular host mail
            for s in chatinfo[0]['mentorSid']:
                for mail,id in s.items():
                    if mail==data["to_be_sent"]:
                        chatm=[]
                        for x in chat_content:
                            if x['role'] == 'mentor' and x['sent_by'] == mail:
                                chatm.append(x)
                            elif x['role'] == 'student' and (x['to_be_sent'] == 'All hosts' or x['to_be_sent'] == mail):
                                chatm.append(x)
                        sio.emit('chat',chatm,to=id)
        #send the student message to him
        sio.emit('chat',chats,to=sid)
    elif data['role'] == 'ment':
        for x in chat_content:
            if x['role'] == 'mentor' and x['sent_by'] == data["email"]:
                chats.append(x)
            elif x['role'] == 'student' and (x['to_be_sent'] == 'All hosts' or x['to_be_sent'] == data["email"]):
                chats.append(x)
        if data["to_be_sent"]=="Everyone":
            for s in chatinfo[0]['studentSid']:
                for mail,id in s.items():
                    chatm=[]
                    for x in chat_content:
                        if x['role'] == 'student' and x['sent_by'] == mail:
                            chatm.append(x)
                        elif x['role'] == 'mentor' and (x['to_be_sent'] == 'Everyone' or x['to_be_sent'] == mail):
                            chatm.append(x)
                    sio.emit('chat',chatm,to=id)
        else:
            #check check to be sent for particular student mail
            for s in chatinfo[0]['studentSid']:
                for mail,id in s.items():
                    if mail==data["to_be_sent"]:
                        chatm=[]
                        for x in chat_content:
                            if x['role'] == 'student' and x['sent_by'] == mail:
                                chatm.append(x)
                            elif x['role'] == 'mentor' and (x['to_be_sent'] == 'Everyone' or x['to_be_sent'] == mail):
                                chatm.append(x)
                        sio.emit('chat',chatm,to=id)
        sio.emit('chat',chats,to=sid)

if __name__ == '__main__':
    port = 8001
    print(f'Starting server on port {port}')
    eventlet.wsgi.server(eventlet.listen(('', port)), app)
