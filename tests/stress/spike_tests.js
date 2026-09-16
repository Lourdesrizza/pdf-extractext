import http from 'k6/http';
import { check } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const pdfFile = open('./pdfs/documento_279_paginas.pdf', 'b');
const endpoint = __ENV.EXTRACT_URL || 'https://pdf-extactext.universidad.localhost/extract';

export const extractDuration = new Trend('pdf_extract_duration', true);
export const successfulResponses = new Counter('pdf_extract_status_200');

export const options = {
  insecureSkipTLSVerify: true,
  stages: [
    { duration: '10s', target: 100 },
    { duration: '20s', target: 100 },
    { duration: '10s', target: 0 },
  ],
};

export default function () {
  const response = http.post(endpoint, pdfFile, {
    headers: { 'Content-Type': 'application/pdf' },
  });

  extractDuration.add(response.timings.duration);
  if (response.status === 200) {
    successfulResponses.add(1);
  }

  check(response, {
    'status == 200': (result) => result.status === 200,
  });
}
