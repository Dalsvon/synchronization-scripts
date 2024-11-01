"""
ContactItem class is based on kotlin class of the same name used in Orechov app. This synchronization service
uses this class to synchronize the database of the app with the data in Orechov website to maintain consistency.

If the class in Orechov app is changed, this class should be changed too.
"""
class ContactItem:
    def __init__(self, title=None, subtitle=None, address=None, coordinates=None, 
                 phone=None, phone2=None, mail=None, web=None, facebook=None, 
                 fbId=None, fbUrl=None, maintenance=None):
        self.title = title
        self.subtitle = subtitle
        self.address = address
        self.coordinates = coordinates
        self.phone = phone
        self.phone2 = phone2
        self.mail = mail
        self.web = web
        self.facebook = facebook
        self.fbId = fbId
        self.fbUrl = fbUrl
        self.maintenance = maintenance

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None and v != ""}
