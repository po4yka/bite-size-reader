from app.db.models import Summary

print(f"Fields: {list(Summary._meta.fields.keys())}")
s = Summary()
print(f"Has attribute: {hasattr(s, 'is_favorited')}")
print(f"Value: {s.is_favorited}")
