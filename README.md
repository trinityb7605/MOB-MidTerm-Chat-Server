# MOB-MidTerm-Chat-Server
MOB cs3720 mid term project WebSocket chat server

## Run the server locally
    cd backend/chat_server
    python -m venv venv ; .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    uvicorn server:app --host 0.0.0.0 --port 8000
Check http://localhost:8000/ -> {"status":"ok","usersOnline":0}

## Point the app at it (frontend/campus-map-frontend/.env)
    EXPO_PUBLIC_CHAT_WS_URL=ws://<your PC's LAN IP>:8000/ws
(Phone/emulator can't use "localhost". Find the IP with `ipconfig`. Leave the line out
 for local-only mode: the chat UI still works, nothing is sent anywhere.)
Restart Expo with `npx expo start -c` after changing .env.

## Test with two devices (two users)
Terminal 1:  npx expo start --port 8081                      -> phone/emulator (u1)
Terminal 2:  $env:EXPO_PUBLIC_USER_ID="u2"; npx expo start --port 8082 -c   -> phone/emulator (u2)

## Note:
Leave the backend alone. The backup/ folder contains all the chat_server files.