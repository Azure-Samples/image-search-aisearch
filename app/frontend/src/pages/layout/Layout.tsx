import { Outlet, Link } from "react-router-dom";
import { SearchBar } from "../../components/SearchBar";
import { SearchResults } from "../../components/SearchResults";
import { useState } from "react";

import github from "../../assets/github.svg";

import styles from "./Layout.module.css";

async function callSearch(text: string) : Promise<{ score: number, url: string }[]> {
    const response = await fetch("/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            "search": text
        })
    })

    return await response.json();
}

const Layout = () => {
    const [images, setImages] = useState<string[]>([])

    const search = async (text: string) =>  {
        const response = await callSearch(text);
        const images = response.map(result => result.url);
        setImages(images)
    }
    return (
        <div className={styles.layout}>
            <header className={styles.header} role={"banner"}>
                <div className={styles.headerContainer}>
                    <Link to="/" className={styles.headerTitleContainer}>
                        <h3 className={styles.headerTitle}>Image Search | Sample</h3>
                    </Link>
                    <nav>
                        <ul className={styles.headerNavList}>
                            <li className={styles.headerNavLeftMargin}>
                                <a href="https://github.com/mattgotteiner/AI-Chat-App-Hack-Vision" target={"_blank"} title="Github repository link">
                                    <img
                                        src={github}
                                        alt="Github logo"
                                        aria-label="Link to github repository"
                                        width="20px"
                                        height="20px"
                                        className={styles.githubLogo}
                                    />
                                </a>
                            </li>
                        </ul>
                    </nav>
                    <h4 className={styles.headerRightText}>Azure AI Search + Azure AI Vision</h4>
                </div>
            </header>
            <div className={styles.container}>
                <div className={styles.searchBar}>
                    <SearchBar
                        clearOnSend={false}
                        disabled={false}
                        placeholder="Type a new question (e.g. does my plan cover annual eye exams?)"
                        onSend={question => search(question)}
                    />
                </div>
                <div className={styles.searchResults}>
                    <SearchResults
                        images={images}
                    />
                </div>
            </div>
            <Outlet />
        </div>
    );
};

export default Layout;
