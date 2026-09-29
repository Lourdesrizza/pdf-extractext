import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const pdfFile = open('./pdfs/documento_279_paginas.pdf', 'b');
const endpoint = __ENV.EXTRACT_URL || 'https://pdf-extactext.universidad.localhost/extract';

export const pdf279Duration = new Trend('pdf_279_duration', true);

export const options = {
  vus: 1,
  iterations: 1,
  hosts: { 'pdf-extactext.universidad.localhost': '127.0.0.1' },
  insecureSkipTLSVerify: true,
  thresholds: {
    pdf_279_duration: ['max<440'],
    checks: ['rate==1'],
  },
};

export default function () {
  const response = http.post(endpoint, pdfFile, {
    headers: { 'Content-Type': 'application/pdf' },
  });

  pdf279Duration.add(response.timings.duration);

  console.log(
    `HTTP ${response.status}; duration=${response.timings.duration.toFixed(2)}ms; ` +
    `sending=${response.timings.sending.toFixed(2)}ms; ` +
    `waiting=${response.timings.waiting.toFixed(2)}ms; ` +
    `receiving=${response.timings.receiving.toFixed(2)}ms; ` +
    `blocked=${response.timings.blocked.toFixed(2)}ms; ` +
    `connecting=${response.timings.connecting.toFixed(2)}ms; ` +
    `tls=${response.timings.tls_handshaking.toFixed(2)}ms`,
  );

  check(response, {
    'status == 200': (result) => result.status === 200,
    'duration < 440 ms': (result) => result.timings.duration < 440,
  });
}
