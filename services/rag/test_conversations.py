"""Chat threads and calendar notes live in RAG, isolated by user."""

from fastapi.testclient import TestClient


def test_chat_and_note_stay_with_the_owner():
    import conversations
    from fastapi import FastAPI

    conversations.reset_memory()
    conversations.bind(None)
    app = FastAPI()
    app.include_router(conversations.router)
    client = TestClient(app)

    created = client.post("/chats", params={"user_id": "user1"})
    assert created.status_code == 201
    chat_id = created.json()["id"]
    assert created.json()["title"] == "New chat"
    assert client.get("/chats", params={"user_id": "user2"}).json()["chats"] == []

    saved = client.put("/notes/2026-10-02", json={"user_id": "user1", "note": "Launch review"})
    assert saved.status_code == 200
    assert saved.json()["saved"] is True
    visible = client.get(
        "/notes", params={"user_id": "user1", "start": "2026-10-01", "end": "2026-10-03"}
    )
    assert visible.json()["notes"] == [{"date": "2026-10-02", "note": "Launch review"}]
    hidden = client.get(
        "/notes", params={"user_id": "user2", "start": "2026-10-01", "end": "2026-10-03"}
    )
    assert hidden.json()["notes"] == []

    client.post(
        f"/chats/{chat_id}/turns",
        json={
            "user_id": "user1",
            "turns": [
                {
                    "role": "user",
                    "text": "What is due?",
                    "files": [{"name": "a.txt", "text": "clause 4"}],
                },
                {"role": "assistant", "text": "Finish the draft."},
            ],
        },
    )
    turns = client.get(f"/chats/{chat_id}/turns", params={"user_id": "user1"})
    assert turns.status_code == 200
    assert turns.json()["turns"][0]["text"] == "What is due?"
    assert "clause 4" not in turns.text
    history = client.get(f"/chats/{chat_id}/history", params={"user_id": "user1"})
    assert history.json()["history"][0]["files"][0]["text"] == "clause 4"
    assert client.get(f"/chats/{chat_id}/turns", params={"user_id": "user2"}).status_code == 404

    renamed = client.patch(
        f"/chats/{chat_id}", params={"user_id": "user1"}, json={"title": "Morning"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Morning"
    assert (
        client.get("/chats", params={"user_id": "user1"}).json()["chats"][0]["title"] == "Morning"
    )
    assert (
        client.patch(
            f"/chats/{chat_id}", params={"user_id": "user2"}, json={"title": "Nope"}
        ).status_code
        == 404
    )
    blank = client.patch(f"/chats/{chat_id}", params={"user_id": "user1"}, json={"title": " "})
    assert blank.status_code == 400

    assert client.delete(f"/chats/{chat_id}", params={"user_id": "user2"}).status_code == 404
    removed = client.delete(f"/chats/{chat_id}", params={"user_id": "user1"})
    assert removed.status_code == 204
    assert client.get("/chats", params={"user_id": "user1"}).json()["chats"] == []
    assert client.get(f"/chats/{chat_id}/turns", params={"user_id": "user1"}).status_code == 404


def test_new_chat_keeps_the_memory_it_references():
    import conversations
    from fastapi import FastAPI

    conversations.reset_memory()
    conversations.bind(None)
    app = FastAPI()
    app.include_router(conversations.router)
    client = TestClient(app)

    created = client.post(
        "/chats",
        params={"user_id": "user1"},
        json={"memory_id": " doc-1 ", "memory_name": " memories-1.docx "},
    )
    assert created.status_code == 201
    assert created.json()["title"] == "New chat"
    assert created.json()["memory"] == {"id": "doc-1", "name": "memories-1.docx"}
    listed = client.get("/chats", params={"user_id": "user1"})
    assert listed.json()["chats"][0]["memory"]["name"] == "memories-1.docx"
    plain = client.post("/chats", params={"user_id": "user1"})
    assert plain.status_code == 201
    assert "memory" not in plain.json()
