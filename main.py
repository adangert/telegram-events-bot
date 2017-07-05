import StringIO
import json
import logging
import random
import urllib
import urllib2
import parsedatetime
import time
import datetime
from dateutil import tz

# for sending images
from PIL import Image
import multipart

# standard app engine imports
from google.appengine.api import urlfetch
from google.appengine.ext import ndb
from google.appengine.api import app_identity
import cloudstorage as gcs
import webapp2

TOKEN = 'ADD YOUR OWN TOKEN HERE'

BASE_URL = 'https://api.telegram.org/bot' + TOKEN + '/'



SESSION_USERS = {}
USER_GROUP_NAME = {}
USER_DATE = {}
USER_START_TIME = {}
USER_END_TIME = {}
USER_EVENT_DESCRIPTION = {}
AUSTIN_CHAT_ID = "-1001049139261"
cal = parsedatetime.Calendar()
# ================================

class Event(ndb.Model):
    # key name: str(chat_id)
    organizer = ndb.StringProperty(indexed=False, default=False)
    organizer_id = ndb.IntegerProperty()
    eventname = ndb.TextProperty()
    day = ndb.DateProperty()
    starttime = ndb.TimeProperty()
    description = ndb.TextProperty()

class SuperMessage(ndb.Model):
    # key name: str(chat_id)
    chat_id = ndb.StringProperty()
    pinned_message_id = ndb.IntegerProperty()

class EnableStatus(ndb.Model):
    # key name: str(chat_id)
    enabled = ndb.BooleanProperty(indexed=False, default=False)


class CST1(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(hours=-6)
    def dst(self, dt):
        return datetime.timedelta(0)
    def tzname(self,dt):
        return "America/Chicago"

class UTC(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(hours=0)
    def dst(self, dt):
        return datetime.timedelta(0)
    def tzname(self,dt):
        return "UTC"

def time_to_cst(t):
    dt = datetime.datetime.combine(datetime.date.today(), t)
    cst_dt = dt.astimezone(CST1())
    return cst_dt.time()

def cst_to_utc(t):
    dt = datetime.datetime.combine(datetime.date.today(), t)
    cst_dt = dt.astimezone(UTC())
    return cst_dt.time()


# ================================


def setEnabled(chat_id, yes):
    es = EnableStatus.get_or_insert(str(chat_id))
    es.enabled = yes
    es.put()

def getEnabled(chat_id):
    es = EnableStatus.get_by_id(str(chat_id))
    if es:
        return es.enabled
    return False

def getfmtevent(event, tmz_info=UTC()):
    # CST = tz.gettz("CST")
    usertime =  event.day.strftime("%A, %B %d")

    # localtime2 = localtime.replace(tzinfo=CST2())
    starttime = time_to_cst(event.starttime.replace(tzinfo=tmz_info)).strftime("%-I:%-M %p").lower()
    return "{}:\n{}\n{}\nstarts at: {}\norganizer: @{}".format(usertime, event.eventname, event.description, starttime, event.organizer)

def getPinStr():
    events = Event.query(ndb.AND(Event.day >= datetime.datetime.now() - datetime.timedelta(hours=10), Event.day < datetime.datetime.now() + datetime.timedelta(days=11))).order(Event.day)
    events_string = ""
    for event in events:
        events_string += getfmtevent(event) + "\n\n"
    pin_string = "UPCOMING EVENTS\n{}\nTo add your own event please talk to @GroupEventsBot".format(events_string)
    return pin_string

def getFullPinStr():
    events = Event.query(Event.day >= datetime.datetime.now() - datetime.timedelta(hours=10)).order(Event.day)
    events_string = ""
    for event in events:
        events_string += getfmtevent(event) + "\n\n"
    pin_string = "ALL FUTURE UPCOMING EVENTS\n\n{}".format(events_string)
    return pin_string

def post_new_event(msg, chat_id):
    resp = urllib2.urlopen(BASE_URL + 'sendMessage', urllib.urlencode({
        'chat_id': str(chat_id),
        'text': msg.encode('utf-8'),
        'disable_web_page_preview': 'true'
    })).read()
    return resp


# ================================



class MeHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        self.response.write(json.dumps(json.load(urllib2.urlopen(BASE_URL + 'getMe'))))

class UpdatePinHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        update_pin()
        self.response.write("pin updated")


class GetUpdatesHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        self.response.write(json.dumps(json.load(urllib2.urlopen(BASE_URL + 'getUpdates'))))


class SetWebhookHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        url = self.request.get('url')
        if url:
            self.response.write(json.dumps(json.load(urllib2.urlopen(BASE_URL + 'setWebhook', urllib.urlencode({'url': url})))))


def update_pin():
    pin_msg = SuperMessage.get_or_insert('SuperMessage')
    pin_chat_id = pin_msg.chat_id
    pinned_message_id = pin_msg.pinned_message_id
    pin_string = getPinStr()
    logging.info('in update pin the chat id is {} and the pinned message to update is {}'.format(pin_chat_id,pinned_message_id))
    resp = urllib2.urlopen(BASE_URL + 'editMessageText', urllib.urlencode({
        'chat_id': str(pin_chat_id),
        'message_id': str(pinned_message_id),
        'text': pin_string + "@",
        'disable_web_page_preview': 'true'
    })).read()

    resp = urllib2.urlopen(BASE_URL + 'editMessageText', urllib.urlencode({
        'chat_id': str(pin_chat_id),
        'message_id': str(pinned_message_id),
        'text': pin_string,
        'disable_web_page_preview': 'true'
    })).read()
    logging.info('edit pin send response:')
    logging.info(resp)
    return resp

class WebhookHandler(webapp2.RequestHandler):

    def post(self):
        urlfetch.set_default_fetch_deadline(60)
        body = json.loads(self.request.body)
        # logging.info('request body:')
        logging.info('request body:' + str(body))
        self.response.write(json.dumps(body))

        update_id = body['update_id']
        try:
            message = body['message']
        except:
            message = body['edited_message']
        message_id = message.get('message_id')
        date = message.get('date')
        text = message.get('text')
        if text is None:
            text = ""
        text = text.encode('utf-8')
        fr = message.get('from')
        username = fr.get('username')
        userid = fr.get('id')
        chat = message['chat']
        chat_type = chat.get('type')
        chat_id = chat['id']
        chat_user = chat.get('username')
        logging.info('the message id was {} and the text was {}'.format(message_id,text))
        message_user_id = message['from']['id']

        if not text:
            logging.info('no text')
            return

        def reply_with_keyboard(msg=None, *args):
            listlist = [[arg] for arg in args]
            # self.create_file('/telegram-events-bot.appspot.com/test_file')
            # self.response.write('\n\n')
            resp = urllib2.urlopen(BASE_URL + 'sendMessage', urllib.urlencode({
                'chat_id': str(chat_id),
                'text': msg.encode('utf-8'),
                'disable_web_page_preview': 'true',
                # 'reply_to_message_id': str(message_id),
                'reply_markup': json.dumps({
                      'keyboard': listlist,


                       'one_time_keyboard': True,
                      'selective': True
                      })
            })).read()


        # def update_pin():
        #     pin_msg = SuperMessage.get_or_insert('SuperMessage')
        #     pin_chat_id = pin_msg.chat_id
        #     pinned_message_id = pin_msg.pinned_message_id
        #     pin_string = getPinStr()
        #     logging.info('in update pin the chat id is {} and the pinned message to update is {}'.format(pin_chat_id,pinned_message_id))
        #     resp = urllib2.urlopen(BASE_URL + 'editMessageText', urllib.urlencode({
        #         'chat_id': str(pin_chat_id),
        #         'message_id': str(pinned_message_id),
        #         'text': pin_string + "@",
        #         'disable_web_page_preview': 'true'
        #     })).read()
        #
        #     resp = urllib2.urlopen(BASE_URL + 'editMessageText', urllib.urlencode({
        #         'chat_id': str(pin_chat_id),
        #         'message_id': str(pinned_message_id),
        #         'text': pin_string,
        #         'disable_web_page_preview': 'true'
        #     })).read()
        #     logging.info('edit pin send response:')
        #     logging.info(resp)
        #     return resp


        def reply(msg, force_reply=False):
            if force_reply:
                resp = urllib2.urlopen(BASE_URL + 'sendMessage', urllib.urlencode({
                    'chat_id': str(chat_id),
                    'text': msg.encode('utf-8'),
                    'disable_web_page_preview': 'true',
                    # 'reply_to_message_id': str(message_id),
                    'reply_markup': json.dumps({
                          'force_reply': True,
                          'selective': True
                          })
                })).read()
            else:
                resp = urllib2.urlopen(BASE_URL + 'sendMessage', urllib.urlencode({
                    'chat_id': str(chat_id),
                    'text': msg.encode('utf-8'),
                    'disable_web_page_preview': 'true',
                })).read()

            # logging.info('reply send response:')
            logging.info('reply send response:' + str(resp))
            return resp

        if chat_type == "supergroup":
            if text == '/pinevents':

                # pin_string = getPinStr()
                # pinned_msg_info = json.loads(reply(pin_string))
                #also need to do admin only
                # if chat_id == AUSTIN_CHAT_ID:
                #this is for a specified admin id to pin events
                if message_user_id == 103787344:
                    pin_string = getPinStr()
                    pinned_msg_info = json.loads(reply(pin_string))
                    reply("Please pin this Event Message")
                    pinned_store = SuperMessage.get_or_insert("SuperMessage")
                    pinned_store.pinned_message_id = int(pinned_msg_info['result']['message_id'])
                    pinned_store.chat_id = str(pinned_msg_info['result']['chat']['id'])
                    pinned_store.put()
                else:
                    reply("Please have an admin pin events")
            elif 'events' in text:
                pin_string = getPinStr()
                reply(pin_string)
                # reply('Please message @GroupEventsBot in a private chat for event commands')
            elif 'createevent' in text:
                reply('Please message @GroupEventsBot in a private chat to create events')
            elif text.startswith('/'):
                sd = text.split()
                if len(sd) > 1:
                    reply("{} turned {} into a {}".format(username, text.split(' ', 1)[1], sd[0].replace("/", "")))
                else:
                    reply("{} is now a {}".format(username, sd[0].replace("/", "")))

        elif chat_type == 'private':
            if "test" in text:
                reply("Hey! this is a test!")
            if text.startswith('/'):
                if text == '/start':
                    reply('Bot enabled')
                    setEnabled(chat_id, True)
                elif text == '/stop':
                    reply('Bot disabled')
                    setEnabled(chat_id, False)
                elif text == '/events':
                    reply(getFullPinStr())
                elif text == "/updatePin":
                    #update_pin()
                    pass
                elif text == '/createevent':
                    reply("Hey there! What would you like the name of the Event to be?\nplease do not use emojis, or special characters for text input")
                    SESSION_USERS[userid] = "EventName"
                else:
                    reply('use /createevent to create your event\ncoming soon: edit your own events + reminders\nIf you need to edit your event after its been created, for now message an admin for the group')

            elif userid in SESSION_USERS:
                if SESSION_USERS[userid] == "EventName":
                    if '\n' in text:
                        reply("please use one line for the event name")
                    else:
                        reply('what day is the event happening on?\n(Events will only show up within a week)\nex: tomorrow, next saturday, June 23, 6/3/2016')
                        USER_GROUP_NAME[userid] = text
                        SESSION_USERS[userid] = "GetDate"


                elif SESSION_USERS[userid] == "GetDate":
                    reply('when does the event start?\nex: 4 pm, 3:25 am')
                    USER_DATE[userid] = cal.parse(text)
                    SESSION_USERS[userid] = "GetStartTime"


                elif SESSION_USERS[userid] == "GetStartTime":
                    reply('what is the event description? (under 400 characters)')
                    USER_START_TIME[userid] = cal.parse(text)
                    SESSION_USERS[userid] = "GetDescription"


                elif SESSION_USERS[userid] == "GetDescription":
                    USER_EVENT_DESCRIPTION[userid] = text
                    if len(text) > 400:
                        reply("description is too long, please keep it under 400 characters, length: " +str(len(text)))
                        reply("what is the event description? (under 400 characters)")
                        SESSION_USERS[userid] = "GetDescription"
                    else:
                        usertime = time.strftime("%B %d", USER_DATE[userid][0])
                        starttime = time.strftime("%I %p", USER_START_TIME[userid][0]).lower()
                        reply("{}:\n{}\n{}\nstarts at: {}\norganizer: @{}".format(usertime, USER_GROUP_NAME[userid], text, starttime, chat_user),force_reply=False)
                        reply_with_keyboard('does this sound right?','yes','no')
                        SESSION_USERS[userid] = "GetConfirmation"

                elif SESSION_USERS[userid] == "GetConfirmation":
                    if "yes" in text:
                        reply("Cool! I'll add it to the events schedule", force_reply=False)
                        SESSION_USERS[userid] = "Done"
                        e = Event(organizer=chat_user,
                                   organizer_id=chat_id,
                                   eventname=USER_GROUP_NAME[userid],
                                   day=datetime.datetime.fromtimestamp(time.mktime(USER_DATE[userid][0])),
                                   starttime=cst_to_utc(datetime.time(USER_START_TIME[userid][0].tm_hour,USER_START_TIME[userid][0].tm_min,tzinfo=CST1())),
                                   description=USER_EVENT_DESCRIPTION[userid])
                        r = e.put()
                        update_pin()
                        event_to_notify = getfmtevent(e, tmz_info=UTC())
                        event_to_notify = "NEW EVENT!!:\n{}".format(event_to_notify)
                        pin_msg = SuperMessage.get_or_insert('SuperMessage')
                        pin_chat_id = pin_msg.chat_id
                        post_new_event(msg=event_to_notify, chat_id=pin_chat_id)
                    else:
                        reply("What would you like the name of the Event to be?")
                        SESSION_USERS[userid] = "EventName"

                        #need to save event and add it to schedule

            elif 'who are you' in text:
                reply('I make the events :D')
            elif 'what time' in text:
                reply('look at the corner of your screen!')
            else:
                if getEnabled(chat_id):
                    reply('use /createevent to create your own event!\ncoming soon: edit your own events + reminders\nIf you need to edit your event after its been created, for now message an admin for the group')
                else:
                    logging.info('not enabled for chat_id {}'.format(chat_id))


app = webapp2.WSGIApplication([
    ('/me', MeHandler),
    ('/updates', GetUpdatesHandler),
    ('/set_webhook', SetWebhookHandler),
    ('/webhook', WebhookHandler),
    ('/updatepin', UpdatePinHandler),
], debug=True)

# import threading
#
# t = threading.Timer(3600.0, update_pin)
# t.start()
