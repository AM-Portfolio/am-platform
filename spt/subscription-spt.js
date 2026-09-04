import http from 'k6/http';
import { check, sleep } from 'k6';

const allScenarios = {
    baseline: {
        executor: 'constant-vus',
        vus: 1,
        duration: '1m',
    },
    load: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '1m', target: 10 },
            { duration: '3m', target: 10 },
            { duration: '1m', target: 0 },
        ],
    },
    stress: {
        executor: 'ramping-vus',
        startVUs: 0,
        stages: [
            { duration: '1m', target: 50 },
            { duration: '2m', target: 50 },
            { duration: '1m', target: 0 },
        ],
    },
};

const selectedScenario = __ENV.SCENARIO;

export const options = {
    scenarios: selectedScenario ? { [selectedScenario]: allScenarios[selectedScenario] } : allScenarios,
    thresholds: {
        http_req_failed: ['rate<0.01'], // Fail rate under 1%
    },
};

let token = null;

export default function () {
    const baseUrl = __ENV.BASE_URL || 'https://am-dev.asrax.in';
    const vuId = __VU;

    // Login dynamically via Identity service to authenticate for Subscription actions
    if (!token) {
        const loginPayload = JSON.stringify({
            username: `spt-user-${vuId}@example.com`,
            password: 'SptPassword.1',
        });
        const loginRes = http.post(`${baseUrl}/identity/auth/login`, loginPayload, {
            headers: { 'Content-Type': 'application/json' },
        });

        if (loginRes.status === 200) {
            token = loginRes.json().access_token;
        } else {
            console.error(`VU ${vuId} failed to log in: ${loginRes.status}`);
            sleep(1);
            return;
        }
    }

    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
    };

    // 1. Fetch Subscription Plans
    const plansRes = http.get(`${baseUrl}/subscriptions/plans`, { headers });
    check(plansRes, {
        'subscription plans list is 200': (r) => r.status === 200,
    });

    sleep(1);

    // 2. Fetch User Active Subscription Details
    const mySubRes = http.get(`${baseUrl}/subscriptions/me`, { headers });
    check(mySubRes, {
        'my subscription details is 200': (r) => r.status === 200,
    });

    sleep(1);

    // 3. Fetch Subscription Usage History
    const usageRes = http.get(`${baseUrl}/subscriptions/usage/history`, { headers });
    check(usageRes, {
        'usage history is 200': (r) => r.status === 200,
    });

    sleep(2);
}
