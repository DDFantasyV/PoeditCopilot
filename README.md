<img src=./PoeditCopilot.png width=256 />

# Poedit Copilot

A copilot software for editing localized **MO/PO** files.<br>
It integrates most commonly used functions, and can realize the functions of importing, comparing, editing, and exporting entries.<br>
In addition, **Poedit Copilot** also provides LLM API to assist in translation.

***
## Feature
- Decode and encode the MO and PO files
- Compare changes between new and old files
- Easier-to-use editor UI interface
- AI translation based on API
***

## Usage
The software contains two windows, **User interface** and **Log**. Normally you can operate in UI and monitor the software in Log.

To start a new project, load the MO files in the order of the top buttons. Once the loading progress is completed, the button will turn green.

The software will automatically compare the old and new entries and list the status.
- **New** - New entry
- **Modified** - Changed entry
- **Deleted** - Deleted entry
- **Normal** - No change

If the entry does not need to be modified, click **Pass** button. If you need to make changes, click **Edit** button.

- Use the **File >> Save** function to temporarily save the project.
- Modify the metadata of the translated file in **Translate >> Metadata**.
- If you need to use the AI translation function, add API key in **Translate >> AI Translate**.
- Remember to change your AI translation language in **Translate >> Target Language**.

After all the work is done, click the last button to export.

***

## Supported API
- Google Gemini 

More in the future...
