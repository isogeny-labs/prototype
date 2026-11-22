// A control, not asking code: it says no to every question and never asks the library. The known-answer check must refuse it.
'use strict';
module.exports = function () {
  return { ownRefusals: [], checkSignature() { return false; } };
};
