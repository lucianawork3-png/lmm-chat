CONTACTS = {
    "lu": "lmonfort@live.com",
    "luciana": "lmonfort@live.com",
}

def resolve_attendees(names: list[str]) -> list[str]:
    emails = []
    for name in names:
        key = name.strip().lower()
        if key in CONTACTS:
            emails.append(CONTACTS[key])
        elif "@" in name:
            emails.append(name.strip())
    return emails
