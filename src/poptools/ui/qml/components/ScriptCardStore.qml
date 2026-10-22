import QtQuick

// Stable ownership outlives delegates and presentation swaps. Moving a face
// changes its visual parent, never its QObject owner or identity.
Item {
    id: root
    visible: false
    property var faces: ({})
    property var borrowed: ({})
    Component {
        id: faceComponent
        MechanicalCardFace {}
    }

    function faceFor(id) {
        let face = peek(id);
        if (!face) {
            // Dynamic QML creation can run bindings/GC. Finish creation before
            // resolving the JS dictionary that receives the QObject wrapper.
            face = faceComponent.createObject(root, {
                objectName: "deckCard_" + id
            });
            if (face) faces[id] = face;
        }
        return face;
    }
    function isBorrowed(id) {
        return borrowed[id] === true;
    }
    function peek(id) {
        return faces[id] || null;
    }
    function lend(id) {
        borrowed[id] = true;
    }
    function unlend(id) {
        delete borrowed[id];
    }
    function borrow(id) {
        lend(id);
        const face = faceFor(id);
        if (!face) unlend(id);
        return face;
    }
    function accept(id, face) {
        faces[id] = face;
        unlend(id);
        face.attachTo(root);
    }
    function mount(id, host, title, icon) {
        if (isBorrowed(id))
            return;
        const face = faceFor(id);
        face.cardTitle = title;
        face.cardIcon = icon || "terminal";
        face.attachTo(host);
    }
    function park(id, host) {
        const face = faces[id];
        if (face && (!host || face.parent === host))
            face.attachTo(root);
    }
}
