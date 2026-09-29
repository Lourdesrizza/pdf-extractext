import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const pdfFile = open('./pdfs/documento_90_paginas.pdf', 'b');
const endpoint = __ENV.EXTRACT_URL || 'https://pdf-extactext.universidad.localhost/extract';

export const pdf90Duration = new Trend('pdf_90_duration', true);

export const options = {
  scenarios: {
    dashboard_90: {
      executor: 'constant-vus',
      vus: 1,
      duration: '45s',
      gracefulStop: '5s',
    },
  },
  hosts: { 'pdf-extactext.universidad.localhost': '127.0.0.1' },
  insecureSkipTLSVerify: true,
  thresholds: {
    checks: ['rate==1'],
  },
};

export default function () {
  const response = http.post(endpoint, pdfFile, {
    headers: { 'Content-Type': 'application/pdf' },
  });

  const duration = response.timings.duration;
  pdf90Duration.add(duration);

  check(response, {
    'status == 200': (result) => result.status === 200,
  });
  console.log(`PDF de 90 páginas: HTTP ${response.status}, ${duration.toFixed(2)} ms`);

  sleep(5);
}
