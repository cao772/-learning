const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('public filtering is progressive, scoped, and resettable', () => {
  const callbacks = {};
  const makeControl = id => ({
    id, value: '', focus() { this.focused = true; },
    addEventListener(type, callback) { callbacks[id + ':' + type] = callback; }
  });
  const search = makeControl('public-search');
  const status = makeControl('public-status');
  status.value = 'all';
  const reset = makeControl('public-reset');
  const tabs = ['all','agent','code'].map(category => ({...makeControl(category), dataset:{category}, classList:{toggle(){}}, setAttribute(){}}));
  const review = {textContent: 'Harness 成本 研究', dataset: {kind: 'reviewed',category:'agent'}, hidden: false};
  const candidate = {textContent: 'Docling 试用线索', dataset: {kind: 'candidate',category:'code'}, hidden: false};
  const reviewEmpty = {hidden: true}, candidateEmpty = {hidden: true};
  const section = (entry, empty) => ({
    querySelectorAll(selector) {
      assert.equal(selector, '[data-public-item]');
      return [entry];
    },
    querySelector(selector) {
      assert.equal(selector, '.public-no-match');
      return empty;
    }
  });
  const elements = {
    'public-search': search, 'public-status': status,
    'public-reset': reset
  };
  const document = {
    getElementById: id => elements[id],
    querySelectorAll: selector => {
      if (selector === '.content-tabs [data-category]') return tabs;
      if (selector === '[data-public-item]') return [review, candidate];
      if (selector === 'section[id="reviewed"], section[id="candidate"]') {
        return [section(review, reviewEmpty), section(candidate, candidateEmpty)];
      }
      throw Error('Unexpected selector: ' + selector);
    }
  };
  const script = fs.readFileSync(path.join(__dirname, '../hub/static/public-filter.js'), 'utf8');
  vm.runInNewContext(script, {document}, {filename: 'public-filter.js'});
  callbacks['code:click']();
  assert.equal(review.hidden,true);
  assert.equal(candidate.hidden,false);
  callbacks['all:click']();
  search.value = 'Harness';
  callbacks['public-search:input']();
  assert.equal(review.hidden, false);
  assert.equal(candidate.hidden, true);
  assert.equal(candidateEmpty.hidden, false);
  search.value = '';
  status.value = 'candidate';
  callbacks['public-status:change']();
  assert.equal(review.hidden, true);
  assert.equal(candidate.hidden, false);
  assert.equal(reviewEmpty.hidden, false);
  callbacks['public-reset:click']();
  assert.equal(search.value, '');
  assert.equal(status.value, 'all');
  assert.equal(search.focused, true);
});
