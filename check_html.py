import re

html = open("/Users/pongo/Desktop/SAVE/ascii studio/ascii_studio.html",
            encoding="utf-8").read()
script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
markup = html.replace(script, "")
ids_in_markup = set(re.findall(r'id="([^"]+)"', markup))
ids_used = set(re.findall(r'\$\("([^"]+)"\)', script))
dyn = set(re.findall(r'\$\("([^"]+)"\s*\+\s*"V"\)', script))
missing = ids_used - ids_in_markup
print("ids used:", len(ids_used), "| ids in markup:", len(ids_in_markup))
print("missing ids:", missing or "NONE")
dups = [i for i in ids_in_markup if markup.count('id="%s"' % i) > 1]
print("dup ids:", dups or "NONE")
ok = True
for tag in ["html", "head", "body", "script", "style", "main", "aside",
            "canvas", "select", "button"]:
    o = len(re.findall(r"<%s[ >]" % tag, html))
    c = html.count("</%s>" % tag)
    if o != c:
        ok = False
    print("tag %-7s open=%d close=%d %s" % (tag, o, c,
                                            "OK" if o == c else "MISMATCH"))
print("dollarV refs valid:", all(i + "V" in ids_in_markup for i in dyn))
print("size: %.1f KB, lines: %d" % (len(html) / 1024, html.count("\n") + 1))
print("STRUCTURE", "OK" if (ok and not missing and not dups) else "FAILED")
