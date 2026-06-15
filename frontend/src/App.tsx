import { useState,useEffect } from 'react';
import Ta from 'react-bootstrap/Button';
import 'bootstrap/dist/css/bootstrap.min.css';
import TextArea from './TextArea';
import {fetch_with_login} from "./common/util"
import { useNavigate } from 'react-router-dom';
import Nikki from './NikkiEditor';
import Tab from 'react-bootstrap/Tab';
import Tabs from 'react-bootstrap/Tabs';
import TemplateEditor from "./TemplateEditor"

function App() {

    return <Tabs
      defaultActiveKey="nikki"
      id="uncontrolled-tab-example"
      className="mb-3"
    >
      <Tab eventKey="nikki" title="日記">
        <Nikki/>
      </Tab>
      <Tab eventKey="template" title="テンプレ">
        <TemplateEditor/>
      </Tab>
    </Tabs>
}

export default App
