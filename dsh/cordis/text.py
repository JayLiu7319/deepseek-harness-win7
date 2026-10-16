"""ECMAScript whitespace shared by frozen text contracts."""
JS_WHITESPACE = '\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'


def has_non_whitespace(text):
    return any(char not in JS_WHITESPACE for char in text)


def trim_js(text):
    return text.strip(JS_WHITESPACE)
