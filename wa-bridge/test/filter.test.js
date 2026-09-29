'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { createFilter } = require('../lib/filter');

const A = '491700000001@c.us';
const B = '491700000002@c.us';

function filter(incomingMode, groups = [], numbers = []) {
    return createFilter({
        incomingMode,
        allowedGroupsLower: groups.map((g) => g.toLowerCase()),
        allowedNumbersSet: new Set(numbers),
    });
}

const group = (name) => ({ isGroup: true, chatName: name, senderPhone: A });
const direct = (phone) => ({ isGroup: false, chatName: 'x', senderPhone: phone });

test('all without lists forwards everything, even unresolved senders', () => {
    const f = filter('all');
    assert.equal(f(group('X')), true);
    assert.equal(f(direct(null)), true);
});

test('disabled forwards nothing', () => {
    assert.equal(filter('disabled')(direct(A)), false);
});

test('groups_only', () => {
    assert.equal(filter('groups_only')(group('X')), true);
    assert.equal(filter('groups_only')(direct(A)), false);
    const f = filter('groups_only', ['Familie']);
    assert.equal(f(group('familie')), true);
    assert.equal(f(group('Arbeit')), false);
    assert.equal(f(group(null)), false, 'unknown name fails closed');
});

test('numbers_only matches resolved phone numbers only', () => {
    const f = filter('numbers_only', [], [A]);
    assert.equal(f(direct(A)), true);
    assert.equal(f(direct(B)), false);
    assert.equal(f(direct(null)), false, 'unresolved LID fails closed');
    assert.equal(f(group('X')), false);
    assert.equal(filter('numbers_only')(direct(A)), false, 'empty list forwards nothing');
});

test('all with both lists: allowed group OR allowed direct number', () => {
    const f = filter('all', ['Familie'], [A]);
    assert.equal(f(group('Familie')), true);
    assert.equal(f(direct(A)), true);
    assert.equal(f(group('Arbeit')), false);
    assert.equal(f(direct(B)), false);
});

test('all with one list restricts to that kind', () => {
    assert.equal(filter('all', ['Familie'])(direct(A)), false);
    assert.equal(filter('all', [], [A])(group('Familie')), false);
});
