import datetime as dt

def log(log_msg, begin="", end="\n"):
    print("%s[%s] : %s" %  (begin, str(dt.datetime.now()), log_msg), end=end)