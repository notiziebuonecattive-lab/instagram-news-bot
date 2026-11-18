"""Buffer GraphQL: lettura canale e singola richiesta shareNow, senza retry sulle scritture."""
import json
import os
import requests

URL = "https://api.buffer.com"


class BufferError(RuntimeError):
    pass


def graphql(query: str, *, token: str | None = None) -> dict:
    api_key = token or os.getenv("BUFFER_API_KEY", "")
    if not api_key:
        raise BufferError("BUFFER_API_KEY mancante")
    try:
        result = requests.post(URL, headers={"Authorization": "Bearer " + api_key,
                                             "Content-Type": "application/json"},
                               json={"query": query}, timeout=35)
        result.raise_for_status()
        body = result.json()
    except (requests.RequestException, ValueError) as exc:
        # Non ripetere automaticamente una POST: un timeout potrebbe avere creato il post.
        raise BufferError(f"Richiesta Buffer di esito incerto: {type(exc).__name__}") from exc
    if body.get("errors"):
        raise BufferError("Errore API GraphQL Buffer: " + str(body["errors"][0].get("message", "sconosciuto"))[:180])
    return body.get("data") or {}


def instagram_channel() -> dict:
    fixed = os.getenv("BUFFER_CHANNEL_ID", "").strip()
    if fixed:
        data = graphql('query { channel(input: { id: ' + json.dumps(fixed) + ' }) { id name service } }')
        channel = data.get("channel")
        if not channel or channel.get("service", "").lower() != "instagram":
            raise BufferError("BUFFER_CHANNEL_ID non corrisponde a un account Instagram")
        return channel
    data = graphql("query { account { organizations { id name } } }")
    organizations = (data.get("account") or {}).get("organizations", [])
    matches = []
    for org in organizations:
        query = 'query { channels(input: { organizationId: ' + json.dumps(org['id']) + ' }) { id name service } }'
        matches += [x for x in (graphql(query).get("channels") or []) if x.get("service", "").lower() == "instagram"]
    if len(matches) != 1:
        raise BufferError(f"Rilevati {len(matches)} canali Instagram. Imposta BUFFER_CHANNEL_ID se sono più di uno")
    return matches[0]


def share_now(*, text: str, image_url: str, channel_id: str) -> str:
    if not image_url.startswith("https://"):
        raise BufferError("L'immagine deve essere pubblica via HTTPS")
    # Valori codificati come stringhe GraphQL, mai concatenati senza escaping.
    query = ("mutation { createPost(input: { text: " + json.dumps(text, ensure_ascii=False)
             + " channelId: " + json.dumps(channel_id)
             + " schedulingType: automatic mode: shareNow assets: [{image: {url: "
             + json.dumps(image_url) + "}}] }) {"
             " ... on PostActionSuccess { post { id text } }"
             " ... on MutationError { message } } }")
    outcome = graphql(query).get("createPost") or {}
    if outcome.get("message"):
        raise BufferError("Buffer non ha accettato il post: " + str(outcome["message"])[:200])
    post_id = (outcome.get("post") or {}).get("id")
    if not post_id:
        raise BufferError("Esito pubblicazione non confermato da Buffer")
    return str(post_id)
