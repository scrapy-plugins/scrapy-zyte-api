import json

from ._page_inputs import Actions, Geolocation, Screenshot

try:
    from web_poet.serialization import SerializedLeafData, register_serialization
except ImportError:
    pass
else:

    def _serialize_Actions(o: Actions) -> SerializedLeafData:
        return {"results.json": json.dumps(o.results).encode()}

    def _deserialize_Actions(cls: type[Actions], data: SerializedLeafData) -> Actions:
        return cls(results=json.loads(data["results.json"]))

    register_serialization(_serialize_Actions, _deserialize_Actions)

    def _serialize_Geolocation(o: Geolocation) -> SerializedLeafData:
        return {}

    def _deserialize_Geolocation(
        cls: type[Geolocation], data: SerializedLeafData
    ) -> Geolocation:
        return cls()

    register_serialization(_serialize_Geolocation, _deserialize_Geolocation)

    def _serialize_Screenshot(o: Screenshot) -> SerializedLeafData:
        return {"body": o.body}

    def _deserialize_Screenshot(
        cls: type[Screenshot], data: SerializedLeafData
    ) -> Screenshot:
        return cls(body=data["body"])

    register_serialization(_serialize_Screenshot, _deserialize_Screenshot)
