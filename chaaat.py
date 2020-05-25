import asyncio
import tornado.escape
import tornado.ioloop
import tornado.locks
import tornado.web
import os.path
import uuid
import requests
import json
import pycurl
import ast
from PIL import Image
import sys
import mysql.connector

from tornado.options import define, options, parse_command_line



define("port", default=8888, help="run on the given port", type=int)
define("debug", default=True, help="run in debug mode")
#####################################


class db:
    def coneectdb():
        mydb = mysql.connector.connect(
        host="127.0.0.1",
        user="hoseinm",
        passwd="123456",
        database="chat",
        auth_plugin="mysql_native_password"
        )
        return mydb

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return  self.get_secure_cookie("user")
        


class MessageBuffer(object):
    def __init__(self):
        # cond is notified whenever the message cache is updated
        self.cond = tornado.locks.Condition()
        self.cache = []
        self.cache_size = 200

    def get_messages_since(self, cursor):
        """Returns a list of messages newer than the given cursor.

        ``cursor`` should be the ``id`` of the last message received.
        """
        results = []
        for msg in reversed(self.cache):
            if msg["id"] == cursor:
                break
            results.append(msg)
        results.reverse()
        return results

    def add_message(self, message):
        self.cache.append(message)
        if len(self.cache) > self.cache_size:
            self.cache = self.cache[-self.cache_size :]
        self.cond.notify_all()


# Making this a non-singleton is left as an exercise for the reader.
global_message_buffer = MessageBuffer()



class MainHandler(BaseHandler):
    def get(self):
        if not self.current_user:
            self.redirect("/register")
            return
        #name = tornado.escape.xhtml_escape(self.current_user)
        #print ("Hello, " + name)
        self.render("index.html", messages=global_message_buffer.cache)
        

class RegisterHandler(BaseHandler):
    def get(self):
        self.render("register.html",error='')
    def post(self):
        username = self.get_argument("name")
        password = self.get_argument("password")
        sql= "SELECT * FROM `user` WHERE `name` = %s "
        test = db.coneectdb()
        mycursor = test.cursor()
        mycursor.execute(sql, (username,))
        myresult = mycursor.fetchall()
        for x in myresult:
            for y in x:
                if y == username :
                    self.render("register.html", error ="username is avilable, select other name or login!!!")
                    return
        sql = "INSERT INTO `user` (`name`, `pass`, `secret`) VALUES ( %s, %s , %s)"
        test = db.coneectdb()
        mycursor = test.cursor()
        val = (username,password, "emty")
        mycursor.execute(sql, val)
        test.commit()
        self.render("login.html",error="user registred")                 
            

class LoginHandler(BaseHandler):
    def get(self):
        self.render("login.html",error='',)
    def post(self):
        username = self.get_argument("name")
        print(username)
        password = self.get_argument("password")
        sql= "SELECT * FROM `user` WHERE `name` = %s "
        test = db.coneectdb()
        mycursor = test.cursor()
        mycursor.execute(sql, (username,))
        myresult = mycursor.fetchall()
        for x in myresult:
            if x[0] == username and x[1] == password :
                self.set_secure_cookie("user", self.get_argument("name"))
                self.redirect("/")

            self.render("login.html", error = "incorrect username or password")

##########username #########
class UsernameFinder(BaseHandler):

    def find_username(self):
        api_url_base = "https://freefeed.net"
        read_my_info = "/v2/users/whoami"
        api_token=tornado.escape.xhtml_escape(self.current_user)
        headers = {'x-authentication-token':api_token}
        response = requests.get(api_url_base+read_my_info,headers=headers)
        content= response.json()
        for k,v in content.items():
            #print(k,v)
            if k == 'users':
                for i,j in v.items():
                    if i=='username':
                        print (j)
                        return(j)
    
    # find screan name  function
    def find_screenName(self):
        api_url_base = "https://freefeed.net"
        read_my_info = "/v2/users/whoami"
        api_token=tornado.escape.xhtml_escape(self.current_user)
        headers = {'x-authentication-token':api_token}
        response = requests.get(api_url_base+read_my_info,headers=headers)
        content= response.json()
        for k,v in content.items():
            if k == 'users':
                for i,j in v.items():
                    if i=='screenName':
                        return(j)    


######## find avatatr  function
    def find_Avatr(self):
        api_url_base = "https://freefeed.net"
        read_my_info = "/v2/users/whoami"
        api_token=tornado.escape.xhtml_escape(self.current_user)
        headers = {'x-authentication-token':api_token}        
        response = requests.get(api_url_base+read_my_info,headers=headers)
        content= response.json()
        for k,v in content.items():
            #print(k,v)
            if k == 'users':
                for i,j in v.items():
                    if i=='profilePictureLargeUrl':
                        return(j)



#######################New message######
class MessageNewHandler(BaseHandler):
    """Post a new message to the chat room."""
    def post(self): 
        img_url = UsernameFinder.find_Avatr(self)
        name = UsernameFinder.find_screenName(self)
        body= self.get_argument("body")
        if not img_url:
            img_url = "https://raw.githubusercontent.com/FreeFeed/freefeed-react-client/e8b6d86f227cc66903e7a06cd9e06cf2e7af3242/assets/images/default-userpic.svg"
        if  name == None :
            name =tornado.escape.xhtml_escape(self.current_user)


        message = {"id": str(uuid.uuid4()), "img_url": str(img_url) ,"name": name ,"body":body}
        #message = {"id": str(uuid.uuid4()), "img_url":img_url ,"name": name ,"body":body}
        
        message["html"] = tornado.escape.to_unicode(
            self.render_string("message.html", message= message)
        )
        
        if self.get_argument("next", None):
            self.redirect(self.get_argument("next"))
        else:
            #name = tornado.escape.xhtml_escape(self.current_user)
            print(type(message))
            self.write(message)
        global_message_buffer.add_message(message)





class MessageUpdatesHandler(tornado.web.RequestHandler):
    """Long-polling request for new messages.

    Waits until new messages are available before returning anything.
    """

    async def post(self):
        cursor = self.get_argument("cursor", None)
        messages = global_message_buffer.get_messages_since(cursor)
        while not messages:
            # Save the Future returned here so we can cancel it in
            # on_connection_close.
            self.wait_future = global_message_buffer.cond.wait()
            try:
                await self.wait_future
            except asyncio.CancelledError:
                return
            messages = global_message_buffer.get_messages_since(cursor)
        if self.request.connection.stream.closed():
            return
        self.write(dict(messages=messages))

    def on_connection_close(self):
        self.wait_future.cancel()



#########################################
##   main 
#########################################

def main():
    tornado.options.parse_command_line()
    application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/login", LoginHandler),
    (r"/register",RegisterHandler),
    (r"/a/message/new", MessageNewHandler),
    (r"/a/message/updates", MessageUpdatesHandler),    
    ], cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
        template_path=os.path.join(os.path.dirname(__file__), "templates"),
        static_path=os.path.join(os.path.dirname(__file__), "static"),
        xsrf_cookies=False,
        debug=options.debug)
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
