import React from 'react';
import ReactDOM from 'react-dom/client';

const rootNode = document.getElementById('app');
const root = ReactDOM.createRoot(rootNode);

const heading = React.createElement("h1", {}, "Hello, World!");
root.render(heading);
