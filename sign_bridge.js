/**
 * Sign Bridge for KGVN Load Tran (Tencent Chaos VM Bridge)
 * Listens on port 19876 by default
 */

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const PORT = parseInt(process.argv[2] || '19876', 10);

// Setup mock window/DOM environment for Chaos VM
global.window = global;
global.document = {
    createElement: () => ({}),
    head: { appendChild: () => {} },
    documentElement: { classList: { add: () => {} } },
    cookie: '',
};
global.location = {
    href: 'https://kgvn-camp.mobagarena.com/app/player-poster',
    hostname: 'kgvn-camp.mobagarena.com',
    search: '',
};
global.navigator = {
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MSDK/5.36.000.9136 mQQAppId/1105779914 mWXAppId/wx7a814e3ceeda8320 mGameId/1137 MSDKDeviceModel/955BC6E3-8E62-467E-8422-329F8582B09A',
};
global.screen = { width: 430, height: 932 };

// Load camp security VM
const secCandidates = [
    path.join(__dirname, 'camp_security.js'),
    path.join(__dirname, 'h5_scripts', '5_camp-security-oversea.0.1.0.js'),
];

let secLoaded = false;
for (const p of secCandidates) {
    if (fs.existsSync(p)) {
        try {
            const code = fs.readFileSync(p, 'utf-8');
            eval(code);
            secLoaded = true;
            break;
        } catch (e) {
            console.error('[SignBridge] Error loading security script from', p, e);
        }
    }
}

if (!secLoaded || !global.__TCSJ__) {
    console.error('[SignBridge] CRITICAL: __TCSJ__ not initialized!');
}

const tcsj = global.__TCSJ__;
const sessions = new Map(); // token -> { roleId, campRoleId, characName, roleJobName, headUrl, rankGradeStar, lastInit }

function apiRequest(endpoint, body, token, encodeparam = null) {
    return new Promise((resolve, reject) => {
        const payload = JSON.stringify(body || {});
        const headers = {
            "Camp-Source": "AOV-CAMP",
            "Camp-Authtype": "msdk",
            "Aov-Region": "1137",
            "Aov-Language": "VN",
            "Msdk-Itopencodeparam": token,
            "Msdk-Gameid": "1137",
            "Msdk-Channelid": "10",
            "Msdk-Os": "2",
            "logicworldid": "1011",
            "areaid": "1",
            "Origin": "https://kgvn-camp.mobagarena.com",
            "Referer": "https://kgvn-camp.mobagarena.com/",
            "User-Agent": global.navigator.userAgent,
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(payload),
        };
        if (encodeparam) {
            headers["Encodeparam"] = encodeparam;
        }

        const req = https.request({
            hostname: 'kgvn-api.mobagarena.com',
            path: endpoint,
            method: 'POST',
            headers: headers,
            timeout: 10000,
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    resolve({ status: res.statusCode, data: JSON.parse(data) });
                } catch (e) {
                    resolve({ status: res.statusCode, raw: data });
                }
            });
        });
        req.on('error', reject);
        req.on('timeout', () => {
            req.destroy(new Error('Request timed out'));
        });
        req.write(payload);
        req.end();
    });
}

async function getOrInitSession(token) {
    if (!token) return null;
    let sess = sessions.get(token);
    if (sess && (Date.now() - sess.lastInit < 5 * 60 * 1000)) {
        return sess;
    }

    try {
        const credRes = await apiRequest('/api/user/game/getcredential', {}, token);
        if (!credRes.data || credRes.data.code !== 0 || !credRes.data.data) {
            console.error('[SignBridge] getcredential failed:', credRes);
            return null;
        }

        const { encryption, roleId } = credRes.data.data;
        tcsj.setLoginRes(encryption, roleId);

        let campRoleId = roleId;
        let characName = null;
        let roleJobName = null;
        let headUrl = null;
        let rankGradeStar = null;

        const firstEncode = tcsj.getEncodeParam(roleId);
        try {
            const selfRes = await apiRequest('/api/user/game/getselfuserinfo', {}, token, firstEncode);
            if (selfRes.data && selfRes.data.data && selfRes.data.data.role) {
                const r = selfRes.data.data.role;
                campRoleId = r.campRoleid || roleId;
                characName = r.characName;
                headUrl = r.headUrl;
                if (r.userGameInfo) {
                    roleJobName = r.userGameInfo.roleJobName;
                    rankGradeStar = r.userGameInfo.rankGradeStar;
                }
            }
        } catch (e) {
            console.warn('[SignBridge] getselfuserinfo warning:', e.message);
        }

        sess = {
            roleId,
            campRoleId,
            characName,
            roleJobName,
            headUrl,
            rankGradeStar,
            lastInit: Date.now()
        };
        sessions.set(token, sess);
        return sess;
    } catch (e) {
        console.error('[SignBridge] Session init exception:', e);
        return null;
    }
}

const server = http.createServer(async (req, res) => {
    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }

    const url = req.url;
    if (req.method === 'GET' && (url === '/' || url === '/health')) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok', time: Date.now(), bridge: 'ChaosVM-v1.0' }));
        return;
    }

    if (req.method === 'POST') {
        let bodyStr = '';
        req.on('data', chunk => bodyStr += chunk);
        req.on('end', async () => {
            let body = {};
            try {
                body = JSON.parse(bodyStr || '{}');
            } catch (e) {}

            try {
                if (url === '/init_session' || url === '/verify') {
                    const token = body.token;
                    const sess = await getOrInitSession(token);
                    if (!sess) {
                        res.writeHead(200, { 'Content-Type': 'application/json' });
                        res.end(JSON.stringify({ code: -1, msg: 'Init session failed or invalid token' }));
                        return;
                    }
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({
                        code: 0,
                        msg: 'ok',
                        data: {
                            roleId: sess.roleId,
                            campRoleId: sess.campRoleId,
                            characName: sess.characName,
                            roleJobName: sess.roleJobName,
                            headUrl: sess.headUrl,
                            rankGradeStar: sess.rankGradeStar
                        }
                    }));
                    return;
                }

                if (url === '/get_encodeparam' || url === '/sign') {
                    const token = body.token || body.fallback_token || body.auth_token;
                    const sess = await getOrInitSession(token);
                    const targetId = body.roleId || (sess ? sess.campRoleId : null);

                    let enc = null;
                    if (tcsj) {
                        enc = tcsj.getEncodeParam(targetId || '');
                    }

                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({
                        code: enc ? 0 : -1,
                        encodeparam: enc,
                        result: enc
                    }));
                    return;
                }

                res.writeHead(404, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Not found' }));
            } catch (err) {
                console.error('[SignBridge] Handler error:', err);
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ code: -1, error: err.message }));
            }
        });
        return;
    }

    res.writeHead(405);
    res.end();
});

server.listen(PORT, '127.0.0.1', () => {
    console.log(`[SignBridge] Server listening on http://127.0.0.1:${PORT}`);
});
