window.onload = function () {
    // Call the V8 extension functions.
    var y = example.foo("x from script.js");  // The arg should start with "x" otherwise raises an exception. y is "foo".
    if (y != "foo") {
        return;
    }

    var ok = false;
    try {
        example.foo(1); // should raise an exception.
    } catch (err) {
        // should run here
        ok = true;
    }
    if (!ok) {
        return;
    }

    // V8 extension functions are OK. Now define bar(). This should be called
    // from Python.
    example.bar = function(x) {
        example.foo(x);
        // Make background green.
        const p = document.getElementById('body_id');
        p.style.backgroundColor = '#008000';
    }
}
