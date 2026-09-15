import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HowToPlay } from "../../src/components/HowToPlay";

describe("HowToPlay", () => {
  it("is closed until the trigger is clicked", () => {
    render(<HowToPlay />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens on the first screen and steps through with Next/Back", async () => {
    const user = userEvent.setup();
    render(<HowToPlay />);

    await user.click(screen.getByRole("button", { name: "How to play" }));
    expect(screen.getByRole("heading", { name: "Welcome to Grudge" })).toBeInTheDocument();
    expect(screen.getByText("1 / 6")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading", { name: "The Prisoner's Dilemma" })).toBeInTheDocument();
    expect(screen.getByText("2 / 6")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("heading", { name: "Welcome to Grudge" })).toBeInTheDocument();
  });

  it("has no Back button on the first screen", async () => {
    const user = userEvent.setup();
    render(<HowToPlay />);
    await user.click(screen.getByRole("button", { name: "How to play" }));
    expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
  });

  it("jumps to a screen via its dot and shows Done on the last screen", async () => {
    const user = userEvent.setup();
    render(<HowToPlay />);
    await user.click(screen.getByRole("button", { name: "How to play" }));

    await user.click(
      screen.getByRole("button", { name: "Go to screen 6: Ranked, Unranked, Simulate" })
    );
    expect(screen.getByRole("heading", { name: "Ranked, Unranked, Simulate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
  });

  it("closes on Escape and reopens on the first screen", async () => {
    const user = userEvent.setup();
    render(<HowToPlay />);

    await user.click(screen.getByRole("button", { name: "How to play" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "How to play" }));
    expect(screen.getByRole("heading", { name: "Welcome to Grudge" })).toBeInTheDocument();
  });

  it("closes when clicking the close button", async () => {
    const user = userEvent.setup();
    render(<HowToPlay />);
    await user.click(screen.getByRole("button", { name: "How to play" }));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on Done at the last screen", async () => {
    const user = userEvent.setup();
    render(<HowToPlay />);
    await user.click(screen.getByRole("button", { name: "How to play" }));
    for (let i = 0; i < 5; i++) {
      await user.click(screen.getByRole("button", { name: "Next" }));
    }
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
