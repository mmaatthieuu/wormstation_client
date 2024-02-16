import cv2
import sys
import os

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from tqdm import tqdm
import csv

import trackpy as tp
import pandas as pd

import numpy as np

class Analyser:
    def __init__(self, visualization=False, output_folder=None):
        self.video_path = None
        self.visualization = visualization
        self.output_folder = output_folder

    def compute_chemotaxis(self, video_path):
        #self.logger.log("Computing chemotaxis")

        print("Use run() instead. Exiting.")
        return

        print(f"Computing chemotaxis for {video_path}")
        self.video_path = video_path
        # self.logger.log("Starting compression of %s" % folder_name)

        # Call the load_video function
        cap, width, height = self.load_video(video_path)

        # Read the first frame
        ret, first_frame = cap.read()
        first_frame = self.get_specific_frame(video_path, 3)

        if not ret:
            print("Error: Could not read the first frame.")
            return

        # Detect edges in the first frame
        # edges = detect_petri_edges(first_frame)

        # Detect circles
        # detected_circles = detect_circles(edges)

        # Save the first frame with detected circles
        # draw_circles(first_frame, detected_circles)

        # get middle of the image width
        middle = int(width / 2)

        # Remove background
        positions = self.locate_worms(video_path)

        # Compute chemotaxis index
        chemotaxis_index_by_frame = self.compute_chemotaxis_index(positions, middle)

        # Save centers of mass to CSV file
        # save_centers_to_csv(positions, 'centers.csv')

        # Save chemotaxis indices to CSV file
        self.save_chemotaxis_indices_to_csv(chemotaxis_index_by_frame, 'data.csv')

        # Plot chemotaxis index
        self.plot_chemotaxis_index(chemotaxis_index_by_frame)

        # Release the video capture object when done
        cap.release()

        return positions

    def run(self, video_path):
        #self.logger.log("Running analysis")
        print(f"Running analysis for {video_path}")

        # Call the load_video function
        cap, width, height = self.load_video(video_path)

        # Read the first frame
        ret, first_frame = cap.read()
        first_frame = self.get_specific_frame(video_path, 3)

        if not ret:
            print("Error: Could not read the first frame.")
            return

        # get middle of the image width
        middle = int(width / 2)

        # Remove background
        positions = self.locate_worms(video_path)

        # Compute chemotaxis index
        chemotaxis_data = self.compute_chemotaxis_index(positions, middle)

        speed_stats = None

        # Initial search_range value
        search_range = 15

        while search_range >= 7:
            try:
                # Compute average velocity with trackpy
                speed_stats, trajectories = self.compute_average_velocity_with_trackpy(positions, search_range)
                print("Tracking complete.")
                break  # Break the loop if successful

            except tp.linking.utils.SubnetOversizeException:
                print(
                    f"Error: The number of particles is too large for linking. Trying with search_range {search_range - 1}.")
                search_range -= 1

        # Release the video capture object when done
        cap.release()

        csv_filename = 'data.csv'
        if self.output_folder is not None:
            # Save data to CSV file
            csv_filename = os.path.join(self.output_folder, 'data.csv')

        try:
            # Save data to CSV file
            self.save_data_to_csv(chemotaxis_data, speed_stats, csv_filename)
        except Exception as e:
            print(f"Error: Could not save data to CSV file: {e}")

        try:
            # Plot chemotaxis index
            self.plot_chemotaxis_data(chemotaxis_data)
        except Exception as e:
            print(f"Error: Could not plot chemotaxis data: {e}")

        try:
            if speed_stats is not None:
                # Plot mean speed
                self.plot_mean_speed(speed_stats)
        except Exception as e:
            print(f"Error: Could not plot mean speed: {e}")




    def get_specific_frame(self, video_path, frame_number):
        # Open the video file
        cap = cv2.VideoCapture(video_path)

        # Check if the video file was successfully opened
        if not cap.isOpened():
            print("Error: Could not open video file.")
            return None  # Return None to indicate an error

        # Set the position to the desired frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number - 1)  # Adjust for 0-based indexing

        # Read the specific frame
        ret, frame = cap.read()

        # Check if the frame was successfully read
        if not ret:
            print(f"Error: Could not read frame {frame_number}.")
            return None  # Return None to indicate an error

        # Release the video capture object when done (do not close OpenCV windows here)
        cap.release()

        # Return the frame
        return frame

    def load_video(self, video_path):
        # Open the video file
        cap = cv2.VideoCapture(video_path)

        # Check if the video file was successfully opened
        if not cap.isOpened():
            print("Error: Could not open video file.")
            return None

        # Get the video's frames per second (fps) and frame dimensions
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"Video loaded successfully. FPS: {fps}, Resolution: {width}x{height}")

        return cap, width, height

    def detect_petri_edges(self, frame):
        # Convert the frame to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Apply GaussianBlur to reduce noise and help edge detection
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)

        # Apply binary thresholding
        _, binary_frame = cv2.threshold(blurred, 50, 255, cv2.THRESH_BINARY)

        # Use Canny edge detection
        edges = cv2.Canny(blurred, 50, 150)

        # cv2.imshow("Binary Frame", binary_frame)

        return edges, binary_frame

    def detect_circles(self, binary_frame, max_distance_from_center=200):
        # Hough Circle Transform parameters
        dp = 1  # Inverse ratio of the accumulator resolution to the image resolution
        min_dist = 500  # Minimum distance between the centers of detected circles
        param1 = 50  # Upper threshold for the internal Canny edge detector
        param2 = 10  # Threshold for center detection
        min_radius = 900  # Minimum radius to be detected
        max_radius = 1500  # Maximum radius to be detected

        # cv2.imshow("Binary Frame", binary_frame)
        # cv2.waitKey(0)

        # Apply Hough Circle Transform
        circles = cv2.HoughCircles(binary_frame, cv2.HOUGH_GRADIENT, dp=dp, minDist=min_dist,
                                   param1=param1, param2=param2, minRadius=min_radius, maxRadius=max_radius)

        if circles is not None:
            # Extract the first detected circle
            circle = circles[0, 0]

            # Reduce the radius by a specific value (adjust as needed)
            circle[2] -= 210

            # Return center and radius
            center = (int(circle[0]), int(circle[1]))
            radius = int(circle[2])

            return center, radius

        return None

    def draw_circles(self, frame, circle_info):
        # not used
        print("draw_circles")
        if circle_info is not None:
            # Convert circle coordinates to integers
            circle_center, circle_radius = circle_info
            circle_center = tuple(map(int, circle_center))
            circle_radius = int(circle_radius)

            # Draw the circle on the frame
            cv2.circle(frame, circle_center, circle_radius, (0, 255, 0), 2)

            # Resize the frame to 50% of its original size
            resized_frame = cv2.resize(frame, (int(frame.shape[1] * 0.5), int(frame.shape[0] * 0.5)))

            # Display the annotated and resized frame
            # cv2.imshow("Annotated and Resized Frame", resized_frame)

            # Wait for a key event and then close the display window
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        else:
            print("No circle detected.")

    def locate_worms(self, video_path, detected_circles=None, min_element_area_threshold=30, stop_at_frame=50):
        # Open the video file
        cap = cv2.VideoCapture(video_path)

        # Check if the video file was successfully opened
        if not cap.isOpened():
            print("Error: Could not open video file.")
            return

        # Create a background subtractor
        bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16.0, detectShadows=False)

        # Dictionary to store the centers of mass for each frame
        all_centers_by_frame = {}

        # Initialize progress bar
        progress_bar = tqdm(total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), desc="Removing Background")

        frame_index = 0  # Index to keep track of the frame number

        # # Check if circles are detected
        # if detected_circles is not None:
        #     # Convert circle coordinates to integers
        #     circle_center, circle_radius = detected_circles
        #     circle_center = tuple(map(int, circle_center))
        #     circle_radius = int(circle_radius)
        #
        # else:
        #     print("No circle detected.")
        #     return

        while True:
            # Read a frame from the video
            ret, frame = cap.read()

            if not ret:
                print("End of video stream.")
                break

            # Apply background subtraction
            fg_mask = bg_subtractor.apply(frame)

            # Set the transparency of the foreground mask
            alpha = 0.5

            # # Create a mask for the detected circle
            # circle_mask = np.zeros_like(fg_mask)
            # cv2.circle(circle_mask, circle_center, circle_radius, (255, 255, 255), thickness=cv2.FILLED)
            #
            # # Apply the mask to the foreground mask
            # fg_mask = cv2.bitwise_and(fg_mask, circle_mask)

            # Remove small elements in the mask based on area threshold
            _, fg_mask_thresh = cv2.threshold(fg_mask, 128, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(fg_mask_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # List to store centers of mass for the current frame
            centers_of_mass = []

            for contour in contours:
                if cv2.contourArea(contour) >= min_element_area_threshold:
                    # Calculate the center of mass
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        center_of_mass = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                        centers_of_mass.append(center_of_mass)

            # Store centers of mass for the current frame in the dictionary
            all_centers_by_frame[frame_index] = centers_of_mass

            # Increment frame index
            frame_index += 1

            # # Convert the foreground mask to a 3-channel image
            # fg_mask_color = cv2.cvtColor(fg_mask, cv2.COLOR_GRAY2BGR)
            #
            # # Display the foreground mask in red
            # fg_mask_color[np.where((fg_mask_color == [255, 255, 255]).all(axis=2))] = [0, 0, 255]
            #
            # # Draw a '+' at each center of mass
            # for center_of_mass in centers_of_mass:
            #     cv2.drawMarker(frame, center_of_mass, (0, 255, 0), markerType=cv2.MARKER_CROSS, markerSize=10, thickness=2)
            #
            # # Blend the original frame and the foreground mask
            # result = cv2.addWeighted(frame, 1 - alpha, fg_mask_color, alpha, 0)
            #
            # # Resize the result frame by 0.5
            # result_resized = cv2.resize(result, (int(result.shape[1] * 0.80), int(result.shape[0] * 0.80)))
            #
            # # Display the blended and resized result
            # cv2.imshow("Blended and Resized Result", result_resized)
            #
            # # Press 'q' to exit the loop and close the windows
            # if cv2.waitKey(30) & 0xFF == ord('q') or frame_index == stop_at_frame:
            #     break

            # Update progress bar
            progress_bar.update(1)

        # Release the video capture object when done
        cap.release()
        cv2.destroyAllWindows()

        return all_centers_by_frame

    def compute_chemotaxis_index(self, all_centers_by_frame, middle):
        # Dictionary to store chemotaxis index and related values for each frame
        chemotaxis_data_by_frame = {}

        # Iterate over frames
        for frame_index, centers_of_mass in all_centers_by_frame.items():
            #print(f"Frame {frame_index}: {len(centers_of_mass)} points detected.")

            # Count points on the left and right sides of the circle
            left_points = sum(1 for center in centers_of_mass if center[0] < middle)
            right_points = sum(1 for center in centers_of_mass if center[0] > middle)

            # Compute chemotaxis index
            total_points = len(centers_of_mass)
            chemotaxis_index = left_points / total_points if total_points > 0 else 0.0

            # print(
            #     f"Frame {frame_index}: {left_points} points on the left, "
            #     f"{right_points} points on the right, chemotaxis index = {chemotaxis_index}")

            # Store chemotaxis data for the current frame
            chemotaxis_data_by_frame[frame_index] = {
                'chemotaxis_index': chemotaxis_index,
                'left_points': left_points,
                'right_points': right_points,
                'total_points': total_points
            }

        return chemotaxis_data_by_frame

    def compute_average_velocity_with_trackpy(self, all_centers_by_frame, frame_rate=2, search_range=15):
        # Convert the dictionary of centers to a DataFrame compatible with trackpy
        df = pd.DataFrame([(frame, x, y) for frame, centers in all_centers_by_frame.items() for x, y in centers],
                          columns=['frame', 'x', 'y'])

        # Use trackpy's link_df to link the points between frames
        linked_df = tp.link_df(df, search_range=search_range, memory=3)

        # Check if 'particle' column exists in the DataFrame
        if 'particle' not in linked_df.columns:
            print("No trajectories found. Check the linking parameters or data quality.")
            return

        # Calculate displacement for each particle between frames
        linked_df['dx'] = linked_df.groupby('particle')['x'].diff()
        linked_df['dy'] = linked_df.groupby('particle')['y'].diff()

        # Calculate velocity in pixels per frame
        linked_df['velocity'] = np.sqrt(linked_df['dx'] ** 2 + linked_df['dy'] ** 2)

        # Exclude frames at boundaries
        #linked_df = linked_df[(linked_df['frame'] > 0) & (linked_df['frame'] < max(linked_df['frame']))]

        # Calculate average and standard deviation of velocity for each frame
        result_df = linked_df.groupby('frame')['velocity'].agg(['mean', 'std']).reset_index()

        # Print or use the result as needed
        #print(result_df)

        # Display images with lines showing assignments
        # self.display_images_with_assignments(result_df['frame'], all_centers_by_frame,
        #                                      result_df['particle'].astype(int),
        #                                      result_df['particle'].astype(int) + 1)

        return result_df, linked_df

    def compute_speed_for_trajectories(self, all_centers_by_frame):
        speeds_by_frame = {}
        for frame in all_centers_by_frame:
            centers = np.array(all_centers_by_frame[frame])
            if len(centers) > 1:
                # Calculate the distance traveled by each trajectory
                distances = np.linalg.norm(np.diff(centers, axis=0), axis=1)
                speeds = distances / 2.0  # Assuming a frame rate of 2 frames per second
                speeds_by_frame[frame] = speeds
            else:
                speeds_by_frame[frame] = np.array([])

        return speeds_by_frame


    def play_movie_with_linked_trajectories(self, video_path, all_centers_by_frame, trajectories):
        # Open the video file
        cap = cv2.VideoCapture(video_path)

        # Check if the video file was successfully opened
        if not cap.isOpened():
            print("Error: Could not open video file.")
            return

        # Set up the figure and axis for animation
        fig, ax = plt.subplots()
        plt.title('Linked Trajectories Overlay')
        plt.xlabel('X')
        plt.ylabel('Y')

        # Function to update the animation frames
        def update(frame):
            # Read a frame from the video
            ret, frame_image = cap.read()

            if not ret:
                print("End of video stream.")
                ani.event_source.stop()
                return

            # Plot the frame
            ax.clear()
            ax.imshow(frame_image)

            # Plot centers for the current frame
            centers = all_centers_by_frame.get(frame, [])
            if centers:
                centers = np.array(centers)
                ax.scatter(centers[:, 0], centers[:, 1], color='red', marker='+')

            # Plot lines connecting particles according to their ID
            for _, row in trajectories[trajectories['frame'] == frame].iterrows():
                particle_id = int(row['particle'])
                if particle_id in trajectories['particle'].values:
                    prev_pos = \
                    trajectories[(trajectories['frame'] == frame - 1) & (trajectories['particle'] == particle_id)][
                        ['x', 'y']].values

                    # Check if prev_pos is not empty
                    if len(prev_pos) > 0:
                        current_pos = row[['x', 'y']].values
                        ax.plot([prev_pos[0, 0], current_pos[0]], [prev_pos[0, 1], current_pos[1]], color='blue')

        # Create an animation
        ani = FuncAnimation(fig, update, frames=len(all_centers_by_frame), interval=50, repeat=False)

        # Display the animation
        plt.show()

        # Release the video capture object when done
        cap.release()
        plt.close()



    def display_images_with_assignments(self, frames, centers_by_frame, row_ind, col_ind):
        for i in range(len(frames) - 1):
            img1 = self.get_specific_frame(self.video_path, frames[i])
            img2 = self.get_specific_frame(self.video_path, frames[i + 1])

            for j, k in zip(row_ind, col_ind):
                pt1 = tuple(centers_by_frame[i][j])
                pt2 = tuple(centers_by_frame[i + 1][k])

                # Draw a line between assigned points
                color = (0, 255, 0)  # Green color for lines
                thickness = 2
                cv2.line(img1, pt1, pt2, color, thickness)
                cv2.circle(img1, pt1, 5, color, -1)
                cv2.circle(img2, pt2, 5, color, -1)

            # Display images with lines
            self.display_two_images(img1, img2, f"Assignment between frames {frames[i]} and {frames[i + 1]}")

    def display_two_images(self, img1, img2, title):
        plt.figure(figsize=(12, 6))
        plt.subplot(1, 2, 1)
        plt.imshow(cv2.cvtColor(img1, cv2.COLOR_BGR2RGB))
        # plt.title(f"Frame {frames[i]}")
        plt.axis('off')

        plt.subplot(1, 2, 2)
        plt.imshow(cv2.cvtColor(img2, cv2.COLOR_BGR2RGB))
        # plt.title(f"Frame {frames[i + 1]}")
        plt.axis('off')

        plt.suptitle(title)
        plt.show()

    def save_centers_to_csv(self, centers_list, csv_filename):
        """
        Save the list of center of mass to a CSV file.

        Parameters:
        - centers_list: List of center of mass, where each element is a tuple (x, y).
        - csv_filename: Name of the CSV file to save.

        Example:
        save_centers_to_csv([(1, 2), (3, 4), (5, 6)], 'centers.csv')
        """
        with open(csv_filename, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(['Frame', 'X', 'Y'])  # Writing header

            for frame, centers in enumerate(centers_list, start=1):
                for center in centers:
                    csv_writer.writerow([frame, center[0], center[1]])

    def save_chemotaxis_indices_to_csv(self, chemotaxis_indices, csv_filename):
        """
        Save the chemotaxis indices to a CSV file.

        Parameters:
        - chemotaxis_indices: Dictionary of chemotaxis indices for each frame.
        - csv_filename: Name of the CSV file to save.

        Example:
        save_chemotaxis_indices_to_csv({1: 0.1, 2: 0.2, 3: 0.3}, 'chemotaxis_indices.csv')
        """
        with open(csv_filename, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(['Frame', 'Chemotaxis Index'])  # Writing header

            for frame, chemotaxis_index in chemotaxis_indices.items():
                csv_writer.writerow([frame, chemotaxis_index])

    import csv

    def save_data_to_csv(self, chemotaxis_data, result_df, csv_filename):
        """
        Save chemotaxis data along with mean speed information to a CSV file.

        Parameters:
        - chemotaxis_data: Dictionary of chemotaxis data for each frame.
        - result_df: DataFrame containing mean speed and speed std for each frame, or None if not available.
        - csv_filename: Name of the CSV file to save.

        Example:
        save_chemotaxis_data_to_csv({1: {'chemotaxis_index': 0.1, 'left_points': 10, 'right_points': 5, 'total_points': 15}},
                                    result_df, 'chemotaxis_data.csv')
        """
        with open(csv_filename, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            header = ['Frame', 'Chemotaxis Index']

            if result_df is not None:
                header += ['Mean Speed', 'Speed Std']

            header += ['Left Points', 'Right Points', 'Total Points']
            csv_writer.writerow(header)  # Writing header

            for frame, chemotaxis_info in chemotaxis_data.items():
                row = [frame, chemotaxis_info['chemotaxis_index']]

                if result_df is not None:
                    mean_speed_info = result_df[result_df['frame'] == frame].iloc[0]
                    row += [mean_speed_info['mean'], mean_speed_info['std']]

                row += [chemotaxis_info['left_points'],
                        chemotaxis_info['right_points'],
                        chemotaxis_info['total_points']]

                csv_writer.writerow(row)

    def plot_chemotaxis_data(self, chemotaxis_data, frame_rate=2, output_prefix="chemotaxis_plot",
                             font_size=14):
        # Extract frame indices
        frame_indices = sorted(chemotaxis_data.keys())

        # Calculate time in minutes for each frame
        time_in_minutes = [frame_index * frame_rate / 60 for frame_index in frame_indices]

        # Extract chemotaxis index values, mean speed, and speed std
        chemotaxis_values = [chemotaxis_data[frame]['chemotaxis_index'] for frame in frame_indices]

        # Plot chemotaxis index with respect to time
        plt.figure(figsize=(10, 6))
        plt.plot(time_in_minutes, chemotaxis_values, marker='o', linestyle='-', color='b', label='Chemotaxis Index')
        plt.title(f'Chemotaxis Index and Mean Speed Over Time', fontsize=font_size)
        plt.xlabel('Time (minutes)', fontsize=font_size)
        plt.ylabel('Chemotaxis Index', fontsize=font_size)
        plt.xticks(fontsize=font_size)
        plt.yticks(fontsize=font_size)

        # Add mean speed information to the plot title
        plt.title(
            f'Chemotaxis Index Time',
            fontsize=font_size)

        # Save the plot as PDF and PNG
        pdf_filename = f"{output_prefix}.pdf"
        png_filename = f"{output_prefix}.png"

        if self.output_folder is not None:
            pdf_filename = os.path.join(self.output_folder, pdf_filename)
            png_filename = os.path.join(self.output_folder, png_filename)

        plt.savefig(pdf_filename, format='pdf')
        plt.savefig(png_filename, format='png')

    def plot_mean_speed(self, result_df, output_prefix="mean_speed_plot", font_size=14):
        # Plot mean speed against frame number
        plt.figure(figsize=(10, 6))
        plt.plot(result_df['frame'], result_df['mean'], label='Mean Speed', color='blue')

        # Plot shaded area for standard deviation
        plt.fill_between(result_df['frame'],
                         result_df['mean'] - result_df['std'],
                         result_df['mean'] + result_df['std'],
                         alpha=0.2, color='blue', label='Standard Deviation')

        # Add labels and title
        plt.xlabel('Frame Number', fontsize=font_size)
        plt.ylabel('Mean Speed (pixels/frame)', fontsize=font_size)
        plt.title('Mean Speed with Standard Deviation', fontsize=font_size)
        plt.xticks(fontsize=font_size)
        plt.yticks(fontsize=font_size)

        # Show legend
        plt.legend()

        # Save the plot as PDF and PNG
        pdf_filename = f"{output_prefix}.pdf"
        png_filename = f"{output_prefix}.png"

        if self.output_folder is not None:
            pdf_filename = os.path.join(self.output_folder, pdf_filename)
            png_filename = os.path.join(self.output_folder, png_filename)

        plt.savefig(pdf_filename, format='pdf')
        plt.savefig(png_filename, format='png')

        if self.visualization:
            # Display the plot
            plt.show()

def main():
    if len(sys.argv) != 2:
        print("Usage: python analyse.py video_path")
        return

    video_path = sys.argv[1]

    # Set the output folder to be the same folder as the input video
    output_folder = os.path.dirname(video_path)

    analyser = Analyser(visualization=False, output_folder=output_folder)

    analyser.run(video_path)

    #positions = analyser.compute_chemotaxis(video_path)
    #speed_stats, trajectories = analyser.compute_average_velocity_with_trackpy(positions)
    #analyser.plot_mean_speed(speed_stats)
    #analyser.play_movie_with_linked_trajectories(video_path, positions, trajectories)

if __name__ == "__main__":
    main()

