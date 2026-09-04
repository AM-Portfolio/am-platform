import http from 'k6/http';
import { check, sleep } from 'k6';

// Define the scenarios for the performance test
export const options = {
    scenarios: {
        baseline: {
            executor: 'constant-vus',
            vus: 1,
            duration: '1m',
        },
        load: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '1m', target: 10 },  // Warm up
                { duration: '3m', target: 10 },  // Hold steady
                { duration: '1m', target: 0 },   // Ramp down
            ],
        },
        stress: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '1m', target: 50 },  // Heavy ramp-up
                { duration: '2m', target: 50 },  // Hold stress load
                { duration: '1m', target: 0 },   // Cool down
            ],
        },
    },
    thresholds: {
        http_req_failed: ['rate<0.01'], // Fail rate must be under 1%
    },
};

// Keep track of the token per Virtual User (VU) thread
let token = null;

export default function () {
    const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
    const vuId = __VU; // Unique ID for this Virtual User thread (1, 2, 3...)

    // 1. Authenticate dynamically as a unique seeded user
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
            console.error(`VU ${vuId} failed to log in: ${loginRes.status} - ${loginRes.body}`);
            sleep(1);
            return;
        }
    }

    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
    };

    // 2. Fetch User Profile
    const profileRes = http.get(`${baseUrl}/identity/users/me`, { headers });
    check(profileRes, {
        'profile status is 200': (r) => r.status === 200,
    });

    sleep(1);

    // 3. Request Account Deletion
    const deletionPayload = JSON.stringify({ feedback: 'SPT load test unique feedback' });
    const deleteRes = http.post(`${baseUrl}/identity/users/me/request-deletion`, deletionPayload, { headers });
    check(deleteRes, {
        'request deletion status is 200': (r) => r.status === 200,
    });

    sleep(1);

    // 4. Restore Account
    const restoreRes = http.post(`${baseUrl}/identity/users/me/restore`, null, { headers });
    check(restoreRes, {
        'restore status is 200': (r) => r.status === 200,
    });

    sleep(2);
}
