'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { errorText, isHarmlessRejection } = require('../lib/errors');

test('errorText', () => {
    assert.equal(errorText(new Error('boom')), 'boom');
    assert.equal(errorText('auth timeout'), 'auth timeout');
    assert.equal(errorText({ code: 1 }), '{"code":1}');
    assert.equal(errorText(undefined), 'undefined');
});

test('isHarmlessRejection', () => {
    const protocol = new Error(
        'Protocol error (Network.getResponseBody): No data found for resource with given identifier',
    );
    assert.equal(isHarmlessRejection(protocol), true);
    assert.equal(isHarmlessRejection(new Error('Target closed')), false);
    assert.equal(isHarmlessRejection('Network.getResponseBody'), false);
});
