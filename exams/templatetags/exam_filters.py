from django import template

register = template.Library()


@register.filter
def mongo_id(obj):
    """Return the string representation of a MongoDB _id field."""
    if isinstance(obj, dict):
        return str(obj.get('_id', ''))
    return str(obj)


@register.filter
def get_item(dictionary, key):
    """Lookup a dictionary value by key (works with ObjectId string keys)."""
    if isinstance(dictionary, dict):
        return dictionary.get(str(key))
    return None
