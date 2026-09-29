import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const pdfFile = open('./pdfs/documento_90_paginas.pdf', 'b');
const endpoint = __ENV.EXTRACT_URL || 'https://pdf-extactext.universidad.localhost/extract';

export const pdf90Duration = new Trend('pdf_90_duration', true);

export const options = {
  vus: 1,
  iterations: 1,
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

  pdf90Duration.add(response.timings.duration);
  console.log(`PDF de 90 páginas: ${response.timings.duration.toFixed(2)} ms`);

  check(response, {
    'status == 200': (result) => result.status === 200,
  });
}
