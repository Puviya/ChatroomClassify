import socketio
import eventlet
import redis
import json
import time


r = redis.Redis(host='localhost', port=6379, db=0)

def insert_chat_content(class_id, chat_content, email,to_be_sent,name,admin):
    email = email.replace('%40', '@')
    present = r.get(class_id)
    # get from mongo if not from redis
    present = json.loads(present.decode('utf-8'))
    # time in format 2021-05-01 12:00:00
    obj = {
        'role': 'mentor' if (email in present[0]['Mentor'] or admin=='true') else 'student',
        'content': chat_content,
        'sent_by': email,
        'uname':name,
        'time': time.strftime("%I:%M%p", time.gmtime()),
        "to_be_sent": to_be_sent,
    }
    chat_data = present[0]['chatContent']
    chat_data.append(obj)
    present[0]['chatContent'] = chat_data
    r.set(class_id, json.dumps(present))
    # store the same data into mongo db here
    # if exception means note it and handle it

def get_chat_content(class_id):
    present = r.get(class_id)
    # if it is not set in redis get it from mongodb
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
    admin = queue_name.split('=')[5].split('&')[0]
    print("connected", token)
    if(classID!='' and r.exists(classID)) :
        chatinfo=r.get(classID)
        if chatinfo != None:
            chatinfo = json.loads(chatinfo.decode('utf-8'))
            if 'src' in chatinfo[0]:
                url = chatinfo[0]['src']
            else:
                url = 'https://live-hls-x6fa.livepush.io/live_cdn/emidfhudvb/index.m3u8'
            if (email in chatinfo[0]['Mentor']) or admin =='true':
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
            # update the same to mongodb
            chat_content = get_chat_content(classID)
            chats = []
            if role == "stud":
                for x in chat_content:
                    if x['role'] == 'student' and x['sent_by'] == email:
                        chats.append(x)
                    elif x['role'] == 'mentor' and (x['to_be_sent'] == 'Everyone' or x['to_be_sent'] == email):
                        chats.append(x)
                #sio.emit('connect',response,to=sid)
            elif role == "ment":
                for x in chat_content:
                    if x['role'] == 'mentor' and (x['sent_by'] == email or x['to_be_sent'] == email or x['to_be_sent'] == 'Everyone'):
                        chats.append(x)
                    elif x['role'] == 'student' and (x['to_be_sent'] =='All hosts' or x['to_be_sent'] == email or x['to_be_sent'] == 'Everyone'):
                        chats.append(x)
            sio.emit('connect',{"chats":chats,"url":url},to=sid)

@sio.on('disconnect')
def disconnect(sid):
    print('Client disconnected:', sid)

@sio.on('getcontents')
def getcontents(sid,data):
    chat_content = get_chat_content(data['classID'])
    chats = []
    if data['role'] == "stud":
        for x in chat_content:
            if x['role'] == 'student' and x['sent_by'] == data['email']:
                chats.append(x)
            elif x['role'] == 'mentor' and (x['to_be_sent'] == 'Everyone' or x['to_be_sent'] == data['email']):
                chats.append(x)
        #sio.emit('connect',response,to=sid)
    elif data['role'] == "ment":
        for x in chat_content:
            if x['role'] == 'mentor' and (x['sent_by'] == data['email'] or x['to_be_sent'] == data['email'] or x['to_be_sent'] == 'Everyone'):
                chats.append(x)
            elif x['role'] == 'student' and (x['to_be_sent'] =='All hosts' or x['to_be_sent'] == data['email']):
                chats.append(x)
    sio.emit('getcontents',chats,to=sid)
@sio.on('switch')
def switch(sid,data):
    chatinfo=r.get(data['classid'])
    chatinfo = json.loads(chatinfo.decode('utf-8'))
    room =[]
    for obj in chatinfo[0]['mentorSid']:
        for j in obj.values():
            room.append(j)
    for obj in chatinfo[0]['studentSid']:
        for j in obj.values():
            room.append(j)
    chatinfo[0]['src']=data['url']
    r.set(data['classid'],json.dumps(chatinfo))
    sio.emit('switch',data['url'],to=room)
@sio.on('chat')
def chat(sid, data):
    #insert the content into the classroom chat
    insert_chat_content(data['classID'], data['chatContent'], data["email"], data['toBeSent'],data['name'],data['isAdmin'])
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
        if data["toBeSent"]=="All hosts":
            #check for all the connected hosts
            for s in chatinfo[0]['mentorSid']:
                #for each connected host get their messages and send to them
                for mail,id in s.items():
                    chatm=[]
                    for x in chat_content:
                        if x['role'] == 'mentor' and (x['sent_by'] == mail or x['to_be_sent'] == mail or x['to_be_sent'] == 'Everyone'):
                            chatm.append(x)
                        elif x['role'] == 'student' and (x['to_be_sent'] == 'All hosts' or x['to_be_sent'] == mail):
                            chatm.append(x)
                    sio.emit('chat',chatm,to=id)
        else:
            #check to be sent for particular host mail
            for s in chatinfo[0]['mentorSid']:
                for mail,id in s.items():
                    if mail==data["toBeSent"]:
                        chatm=[]
                        for x in chat_content:
                            if x['role'] == 'mentor' and (x['sent_by'] == mail or x['to_be_sent'] == mail or x['to_be_sent'] == 'Everyone'):
                                chatm.append(x)
                            elif x['role'] == 'student' and (x['to_be_sent'] == 'All hosts' or x['to_be_sent'] == mail):
                                chatm.append(x)
                        sio.emit('chat',chatm,to=id)
        #send the student message to him
        sio.emit('chat',chats,to=sid)
    elif data['role'] == 'ment':
        for x in chat_content:
            if x['role'] == 'mentor' and (x['sent_by'] == data["email"] or x['to_be_sent'] == data["email"] or x['to_be_sent'] == 'Everyone'):
                chats.append(x)
            elif x['role'] == 'student' and (x['to_be_sent'] == 'All hosts' or x['to_be_sent'] == data["email"]):
                chats.append(x)
        if data["toBeSent"]=="Everyone":
            for s in chatinfo[0]['studentSid']:
                for mail,id in s.items():
                    chatm=[]
                    for x in chat_content:
                        if x['role'] == 'student' and x['sent_by'] == mail:
                            chatm.append(x)
                        elif x['role'] == 'mentor' and (x['to_be_sent'] == 'Everyone' or x['to_be_sent'] == mail):
                            chatm.append(x)
                    sio.emit('chat',chatm,to=id)
            for s in chatinfo[0]['mentorSid']:
                #for each connected host get their messages and send to them
                for mail,id in s.items():
                    chatm=[]
                    for x in chat_content:
                        if x['role'] == 'mentor' and (x['sent_by'] == mail or x['to_be_sent'] == mail or x['to_be_sent'] == 'Everyone'):
                            chatm.append(x)
                        elif x['role'] == 'student' and (x['to_be_sent'] == 'All hosts' or x['to_be_sent'] == mail):
                            chatm.append(x)
                    sio.emit('chat',chatm,to=id)
        else:
            #check check to be sent for particular student mail
            for s in chatinfo[0]['studentSid']:
                for mail,id in s.items():
                    if mail==data["toBeSent"]:
                        chatm=[]
                        for x in chat_content:
                            if x['role'] == 'student' and x['sent_by'] == mail:
                                chatm.append(x)
                            elif x['role'] == 'mentor' and (x['to_be_sent'] == 'Everyone' or x['to_be_sent'] == mail):
                                chatm.append(x)
                        sio.emit('chat',chatm,to=id)
            for s in chatinfo[0]['mentorSid']:
                for mail,id in s.items():
                    if mail==data["toBeSent"]:
                        chatm=[]
                        for x in chat_content:
                            if x['role'] == 'mentor' and (x['sent_by'] == mail or x['to_be_sent'] == mail or x['to_be_sent'] == 'Everyone'):
                                chatm.append(x)
                            elif x['role'] == 'student' and (x['to_be_sent'] == 'All hosts' or x['to_be_sent'] == mail):
                                chatm.append(x)
                        sio.emit('chat',chatm,to=id)
        sio.emit('chat',chats,to=sid)
@sio.on('meetEnded')
def meetEnded(sid,data):
    chatinfo=r.get(data["classid"])
    chatinfo = json.loads(chatinfo.decode('utf-8'))
    room =[]
    for obj in chatinfo[0]['mentorSid']:
        for j in obj.values():
            room.append(j)
    for obj in chatinfo[0]['studentSid']:
        for j in obj.values():
            room.append(j)
    sio.emit('meetEnded',to=room)

@sio.on('banner')
def banner(sid,data):
    r.set('banner',data)
    res=r.get('banner')
    sio.emit('banner',res,to=sid)

@sio.on('bannerGet')
def bannerGet(sid):
    if not r.exists('banner'):
        # If the banner key doesn't exist, set it to 'enable'
        r.set('banner', 'enable')
    res=r.get('banner')
    val=''
    val += res.decode('utf-8')
    sio.emit('bannerGet',val,to=sid)
@sio.on('alertModal')
def AlertMessage(sid,data):
    if data['for'] == 'switchalert':
        sio.emit('alertSwitch',data['time'],to=sid)
    elif data['for'] == 'endalert':
        sio.emit('alertEnd',data['time'],to=sid)
@sio.on('dropDown')
def AddDropDown(sid,data):
    sio.emit('updateDropdown',data)
if __name__ == '__main__':
    port = 8001
    print(f'Starting server on port {port}')
    eventlet.wsgi.server(eventlet.listen(('', port)), app)
