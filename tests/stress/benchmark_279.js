import http from 'k6/http';
import { check } from 'k6';
import { Trend } from 'k6/metrics';

const pdfFile = open('./pdfs/documento_279_paginas.pdf', 'b');
const endpoint = __ENV.EXTRACT_URL || 'https://pdf-extactext.universidad.localhost/extract';

export const pdf279Duration = new Trend('pdf_279_duration', true);

export const options = {
  vus: 1,
  iterations: 1,
  insecureSkipTLSVerify: true,
  thresholds: {
    pdf_279_duration: ['max<440'],
  },
};

export default function () {
  const response = http.post(endpoint, pdfFile, {
    headers: { 'Content-Type': 'application/pdf' },
  });

  pdf279Duration.add(response.timings.duration);

  check(response, {
    'status == 200': (result) => result.status === 200,
    'duration < 440 ms': (result) => result.timings.duration < 440,
  });
}
