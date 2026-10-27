"use strict";

const test = require("node:test");
const assert = require("node:assert");
const { gaweAvailable } = require("./mode.js");

const card = { title: "Backend Engineer", url: "https://id.jobstreet.com/job/1234567" };
const detail = { title: "Backend Engineer", description: "Requirements: Go" };

test("detail page without cards offers only the full description", () => {
  assert.deepStrictEqual(gaweAvailable({ jobs: [], detail }), { cards: false, detail: true });
});

test("search page without a detail panel offers only cards", () => {
  assert.deepStrictEqual(gaweAvailable({ jobs: [card], detail: null }), {
    cards: true,
    detail: false,
  });
});

test("split view offers both actions at once", () => {
  assert.deepStrictEqual(gaweAvailable({ jobs: [card], detail }), { cards: true, detail: true });
});

test("page with neither offers nothing", () => {
  assert.deepStrictEqual(gaweAvailable({ jobs: [], detail: null }), {
    cards: false,
    detail: false,
  });
});

test("detail object without a description does not enable the detail action", () => {
  assert.deepStrictEqual(gaweAvailable({ jobs: [], detail: { title: "Backend Engineer" } }), {
    cards: false,
    detail: false,
  });
});
